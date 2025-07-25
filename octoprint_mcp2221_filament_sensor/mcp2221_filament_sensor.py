# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

import time
import threading
import logging
from collections import deque
from typing import Optional, Dict, Any, List

import octoprint.plugin
import octoprint.printer
import octoprint.filemanager
import flask
from octoprint.events import Events

try:
    import EasyMCP2221

    MCP2221A_AVAILABLE = True
except ImportError:
    MCP2221A_AVAILABLE = False


class MockMCP2221A:
    """Mock MCP2221A for testing without hardware"""

    def __init__(self):
        self._pins = {0: False, 1: False, 2: False, 3: False}
        self._last_values = {0: False, 1: False, 2: False, 3: False}
        self.is_connected = True
        self._runout_triggered = {0: False, 2: False}  # Track if runout already triggered
        self._motion_counter = 0

    def GPIO_read(self):
        """Simulate GPIO reading - returns tuple (gp0, gp1, gp2, gp3) to match EasyMCP2221 API"""
        import random

        # Make mock sensors much less aggressive - only trigger occasionally for testing
        # GP0 (E0 runout sensor) - much lower chance of false runouts
        if not self._runout_triggered[0] and random.random() > 0.9999:  # 0.01% chance
            self._runout_triggered[0] = True
        elif self._runout_triggered[0] and random.random() > 0.95:  # 5% chance to clear
            self._runout_triggered[0] = False
        gp0 = not self._runout_triggered[0]  # True = filament present

        # GP1 (E0 motion sensor) - simulate more realistic motion
        self._motion_counter += 1
        gp1 = (self._motion_counter % 20) < 10  # Regular pulse pattern

        # GP2 (E1 runout sensor) - much lower chance of false runouts
        if not self._runout_triggered[2] and random.random() > 0.9999:  # 0.01% chance
            self._runout_triggered[2] = True
        elif self._runout_triggered[2] and random.random() > 0.95:  # 5% chance to clear
            self._runout_triggered[2] = False
        gp2 = not self._runout_triggered[2]  # True = filament present

        # GP3 (E1 motion sensor) - simulate more realistic motion
        gp3 = (
            (self._motion_counter + 10) % 20
        ) < 10  # Regular pulse pattern, offset from GP1

        return (gp0, gp1, gp2, gp3)

    def set_pin_function(self, **kwargs):
        """Mock pin configuration - accepts gp0, gp1, gp2, gp3 kwargs"""
        pass

    def close(self):
        self.is_connected = False


class SensorState:
    """Track individual sensor state and history"""
    
    def __init__(self, pin: int, sensor_type: str, inverted: bool = False, debounce_time: float = 0.1):
        self.pin = pin
        self.sensor_type = sensor_type  # 'runout' or 'motion'
        self.inverted = inverted
        self.debounce_time = debounce_time
        
        self.current_state = False
        self.last_stable_state = False
        self.last_change_time = 0
        self.last_trigger_time = 0
        
        # Motion-specific tracking
        if sensor_type == 'motion':
            self.motion_history = deque(maxlen=100)  # Keep last 100 readings
            self.last_motion_time = time.time()
            
    def update(self, raw_value: bool) -> bool:
        """Update sensor state with debouncing. Returns True if state changed."""
        current_time = time.time()
        processed_value = not raw_value if self.inverted else raw_value
        
        # Debounce logic
        if processed_value != self.current_state:
            if current_time - self.last_change_time > self.debounce_time:
                old_state = self.last_stable_state
                self.last_stable_state = processed_value
                self.last_change_time = current_time
                
                # Track motion pulses
                if self.sensor_type == 'motion' and processed_value:
                    self.motion_history.append(current_time)
                    self.last_motion_time = current_time
                    
                return old_state != self.last_stable_state
                
        self.current_state = processed_value
        return False
        
    def get_motion_timeout_status(self, timeout_seconds: float) -> bool:
        """Check if motion has timed out"""
        if self.sensor_type != 'motion':
            return False
        return (time.time() - self.last_motion_time) > timeout_seconds
        
    def get_motion_rate(self, window_seconds: float = 10.0) -> float:
        """Get motion rate (pulses per second) over the specified window"""
        if self.sensor_type != 'motion':
            return 0.0
            
        current_time = time.time()
        cutoff_time = current_time - window_seconds
        
        # Count pulses in the time window
        recent_pulses = [t for t in self.motion_history if t >= cutoff_time]
        return len(recent_pulses) / window_seconds


class MCP2221FilamentSensorPlugin(
    octoprint.plugin.SettingsPlugin,
    octoprint.plugin.AssetPlugin,
    octoprint.plugin.TemplatePlugin,
    octoprint.plugin.StartupPlugin,
    octoprint.plugin.ShutdownPlugin,
    octoprint.plugin.EventHandlerPlugin,
    octoprint.plugin.ProgressPlugin,
    octoprint.plugin.SimpleApiPlugin,
    octoprint.plugin.BlueprintPlugin,
):

    def __init__(self):
        self._logger = logging.getLogger("octoprint.plugins.mcp2221_filament_sensor")

        # Hardware interface
        self.mcp = None
        self.use_mock = False

        # Sensor objects
        self.sensors = {}  # Dict of extruder -> {'runout': SensorState, 'motion': SensorState}

        # Monitoring
        self.monitoring_thread = None
        self.monitoring_active = False
        self.monitor_lock = threading.Lock()

        # State tracking
        self.current_extruder = 0
        self.is_printing = False
        self.print_paused = False
        self.last_gcode_analysis = {}

        # Trigger tracking
        self.triggered_extruders = set()  # Track which extruders have triggered sensors

    ##~~ SettingsPlugin mixin

    def get_settings_defaults(self):
        return {
            # Hardware settings
            "use_mock": False,
            "poll_interval": 0.01,  # Fast polling for event-like behavior (10ms)
            
            # Extruder 0 settings
            "e0_enabled": True,
            "e0_runout_pin": 0,
            "e0_runout_inverted": False,
            "e0_motion_pin": 1,
            "e0_motion_inverted": False,
            "e0_motion_timeout": 30.0,  # 30 seconds before motion timeout
            "e0_debounce_time": 0.5,   # 500ms debounce to prevent false triggers
            
            # Extruder 1 settings
            "e1_enabled": True,
            "e1_runout_pin": 2,
            "e1_runout_inverted": False,
            "e1_motion_pin": 3,
            "e1_motion_inverted": False,
            "e1_motion_timeout": 30.0,  # 30 seconds before motion timeout
            "e1_debounce_time": 0.5,   # 500ms debounce to prevent false triggers
            
            # G-code action settings (one field per error type)
            "runout_gcode": "M600\n; Filament runout detected\nM117 Insert filament and resume",
            "motion_timeout_gcode": "@pause\n; No motion detected - possible jam\nM117 Check for filament jam",
            
            # Advanced settings
            "prevent_print_start": False,  # Prevent starting print without filament
            "only_active_extruder": True,  # Only monitor currently active extruder
            "notification_enabled": True,
            
            # Debug settings
            "debug_logging": False,
        }

    def on_settings_save(self, data):
        old_debug = self._settings.get_boolean(["debug_logging"])

        octoprint.plugin.SettingsPlugin.on_settings_save(self, data)

        # Update debug logging level
        new_debug = self._settings.get_boolean(["debug_logging"])
        if old_debug != new_debug:
            if new_debug:
                self._logger.setLevel(logging.DEBUG)
            else:
                self._logger.setLevel(logging.INFO)

        # Restart monitoring with new settings
        self._restart_monitoring()

    ##~~ AssetPlugin mixin

    def get_assets(self):
        return {
            "js": ["js/mcp2221_filament_sensor.js"],
            "css": ["css/mcp2221_filament_sensor.css"],
        }

    ##~~ TemplatePlugin mixin

    def get_template_configs(self):
        return [
            {
                "type": "settings",
                "template": "mcp2221_filament_sensor_settings.jinja2",
                "custom_bindings": True,
            }
        ]

    ##~~ StartupPlugin mixin

    def on_after_startup(self):
        self._logger.info("MCP2221A Filament Sensor Plugin starting up...")

        # Set debug logging if enabled
        if self._settings.get_boolean(["debug_logging"]):
            self._logger.setLevel(logging.DEBUG)

        # Initialize printer state from OctoPrint's current state
        try:
            if hasattr(self._printer, "is_printing") and self._printer.is_printing():
                self.is_printing = True
                self._logger.info(
                    "Plugin started during active print - enabling monitoring"
                )
            else:
                self.is_printing = False
                self._logger.info("Plugin started with no active print")
        except Exception as e:
            self._logger.warning(f"Could not determine initial print state: {e}")
            self.is_printing = False

        # Initialize hardware
        self._initialize_hardware()

        # Start monitoring
        self._start_monitoring()

    ##~~ ShutdownPlugin mixin

    def on_shutdown(self):
        self._logger.info("MCP2221A Filament Sensor Plugin shutting down...")
        self._stop_monitoring()
        self._cleanup_hardware()

    ##~~ EventHandlerPlugin mixin

    def on_event(self, event, payload):
        if event == Events.PRINT_STARTED:
            self.is_printing = True
            self.print_paused = False
            self.triggered_extruders.clear()
            self._logger.info(
                f"Print started - enabling sensor monitoring (is_printing={self.is_printing})"
            )

        elif event == Events.PRINT_DONE or event == Events.PRINT_FAILED or event == Events.PRINT_CANCELLED:
            self.is_printing = False
            self.print_paused = False
            self.triggered_extruders.clear()
            self._logger.info(
                f"Print ended ({event}) - disabling runout actions (is_printing={self.is_printing})"
            )

        elif event == Events.PRINT_PAUSED:
            self.print_paused = True
            self._logger.info(
                f"Print paused (is_printing={self.is_printing}, print_paused={self.print_paused})"
            )

        elif event == Events.PRINT_RESUMED:
            self.print_paused = False
            self.triggered_extruders.clear()  # Reset triggers on resume
            self._logger.info(
                f"Print resumed - resetting sensor triggers (is_printing={self.is_printing}, print_paused={self.print_paused})"
            )

    ##~~ ProgressPlugin mixin

    def on_print_progress(self, storage, path, progress):
        # This is called during printing, we can use it to track print state
        pass

    ##~~ GcodeHook to track extruder changes

    def process_gcode(self, comm_instance, phase, cmd, cmd_type, gcode, *args, **kwargs):
        """Track extruder changes via T commands"""
        if gcode and gcode.startswith('T'):
            try:
                extruder_num = int(gcode[1:])
                if extruder_num in [0, 1]:
                    old_extruder = self.current_extruder
                    self.current_extruder = extruder_num
                    if old_extruder != self.current_extruder:
                        self._logger.debug(f"Active extruder changed to E{self.current_extruder}")
            except (ValueError, IndexError):
                pass  # Invalid T command, ignore

        return cmd

    ##~~ SimpleApiPlugin mixin

    def is_api_adminonly(self):
        return False

    def is_api_protected(self):
        return False  # Disable CSRF protection

    def get_api_commands(self):
        return dict(
            get_status=[],
            test_sensors=[]
        )

    def on_api_command(self, command, data):
        """Handle API commands"""
        if command == "get_status":
            return flask.jsonify(self._get_status())
        elif command == "test_sensors":
            return flask.jsonify(self._test_sensors())

    def on_api_get(self, request):
        """Handle API GET requests - return status"""
        return flask.jsonify(self._get_status())

    def _get_status(self):
        """Get current sensor status"""
        status = {
            "hardware_connected": self.mcp is not None and (self.use_mock or getattr(self.mcp, 'is_connected', False)),
            "is_printing": self.is_printing,
            "current_extruder": self.current_extruder,
            "use_mock": getattr(self, 'use_mock', False),
            "sensors": {}
        }

        for extruder_idx in [0, 1]:
            if extruder_idx in self.sensors:
                extruder_sensors = self.sensors[extruder_idx]
                status["sensors"][f"e{extruder_idx}"] = {
                    "runout": {
                        "state": extruder_sensors["runout"].last_stable_state,
                        "pin": extruder_sensors["runout"].pin,
                        "triggered": extruder_idx in self.triggered_extruders
                    },
                    "motion": {
                        "state": extruder_sensors["motion"].last_stable_state,
                        "pin": extruder_sensors["motion"].pin,
                        "last_motion": extruder_sensors["motion"].last_motion_time,
                        "timeout": extruder_sensors["motion"].get_motion_timeout_status(
                            self._settings.get_float([f"e{extruder_idx}_motion_timeout"])
                        ),
                        "rate": extruder_sensors["motion"].get_motion_rate()
                    }
                }

        return status

    def _test_sensors(self):
        """Test sensor functionality"""
        if not self.mcp:
            return {"error": "Hardware not connected"}

        try:
            if hasattr(self.mcp, "GPIO_read"):
                readings = self.mcp.GPIO_read()
                return {
                    "test_result": "success",
                    "raw_readings": readings,
                    "timestamp": time.time(),
                }
            else:
                return {"error": "GPIO read method not available"}
        except Exception as e:
            self._logger.exception("Error testing sensors")
            return {"error": str(e)}

    # BlueprintPlugin mixin methods
    def is_blueprint_csrf_protected(self):
        """Define CSRF protection for blueprint routes"""
        return True

    def is_blueprint_protected(self):
        """Define authentication protection for blueprint routes"""
        return False

    @octoprint.plugin.BlueprintPlugin.route("/status", methods=["GET"])
    def blueprint_api_status(self):
        """Blueprint route for sensor status"""
        return flask.jsonify(self._get_status())

    @octoprint.plugin.BlueprintPlugin.route("/test", methods=["POST"])
    def blueprint_api_test(self):
        """Blueprint route for sensor testing"""
        return flask.jsonify(self._test_sensors())

    ##~~ Hardware Management

    def _initialize_hardware(self):
        """Initialize MCP2221A hardware connection"""
        self.use_mock = self._settings.get_boolean(["use_mock"])

        if self.use_mock or not MCP2221A_AVAILABLE:
            self._logger.info("Using mock MCP2221A for testing")
            self.mcp = MockMCP2221A()
            self.use_mock = True
        else:
            try:
                self.mcp = EasyMCP2221.Device()
                # Configure pins as GPIO inputs for sensor reading
                self.mcp.set_pin_function(
                    gp0="GPIO_IN",  # E0 runout sensor
                    gp1="GPIO_IN",  # E0 motion sensor
                    gp2="GPIO_IN",  # E1 runout sensor
                    gp3="GPIO_IN",  # E1 motion sensor
                )
                self._logger.info("EasyMCP2221 hardware initialized successfully")
            except Exception as e:
                self._logger.error(f"Failed to initialize MCP2221A hardware: {e}")
                self._logger.info("Falling back to mock mode")
                self.mcp = MockMCP2221A()
                self.use_mock = True

        # Initialize sensor objects
        self._initialize_sensors()

    def _initialize_sensors(self):
        """Initialize sensor state objects based on settings"""
        self.sensors.clear()

        for extruder_idx in [0, 1]:
            if self._settings.get_boolean([f"e{extruder_idx}_enabled"]):
                # Runout sensor
                runout_sensor = SensorState(
                    pin=self._settings.get_int([f"e{extruder_idx}_runout_pin"]),
                    sensor_type="runout",
                    inverted=self._settings.get_boolean([f"e{extruder_idx}_runout_inverted"]),
                    debounce_time=self._settings.get_float([f"e{extruder_idx}_debounce_time"])
                )

                # Motion sensor
                motion_sensor = SensorState(
                    pin=self._settings.get_int([f"e{extruder_idx}_motion_pin"]),
                    sensor_type="motion",
                    inverted=self._settings.get_boolean([f"e{extruder_idx}_motion_inverted"]),
                    debounce_time=self._settings.get_float([f"e{extruder_idx}_debounce_time"])
                )

                self.sensors[extruder_idx] = {
                    "runout": runout_sensor,
                    "motion": motion_sensor
                }

                self._logger.info(f"Initialized sensors for E{extruder_idx}: "
                                f"runout=pin{runout_sensor.pin}, motion=pin{motion_sensor.pin}")

    def _cleanup_hardware(self):
        """Clean up hardware connections"""
        if self.mcp and hasattr(self.mcp, 'close'):
            try:
                self.mcp.close()
            except Exception as e:
                self._logger.error(f"Error closing MCP2221A: {e}")
        self.mcp = None

    ##~~ Monitoring

    def _start_monitoring(self):
        """Start the sensor monitoring thread"""
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            return

        self.monitoring_active = True
        self.monitoring_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitoring_thread.start()
        self._logger.info("Sensor monitoring thread started")

    def _stop_monitoring(self):
        """Stop the sensor monitoring thread"""
        self.monitoring_active = False
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            self.monitoring_thread.join(timeout=2.0)
        self._logger.info("Sensor monitoring thread stopped")

    def _restart_monitoring(self):
        """Restart monitoring with new settings"""
        self._stop_monitoring()
        self._initialize_sensors()
        self._start_monitoring()

    def _monitoring_loop(self):
        """Main sensor monitoring loop - optimized for pulse detection"""
        base_poll_interval = self._settings.get_float(["poll_interval"])

        while self.monitoring_active:
            try:
                # Adaptive polling rate based on print status
                if self.is_printing and not self.print_paused:
                    # Fast polling during active printing for motion pulse detection
                    poll_interval = min(base_poll_interval, 0.005)  # 5ms max during printing
                else:
                    # Slower polling when idle to conserve CPU
                    poll_interval = max(base_poll_interval, 0.1)   # 100ms min when idle

                with self.monitor_lock:
                    self._check_sensors()

                time.sleep(poll_interval)

            except Exception as e:
                self._logger.error(f"Error in monitoring loop: {e}")
                time.sleep(1.0)  # Longer delay on error

    def _check_sensors(self):
        """Check all sensors and handle triggers"""
        if not self.mcp:
            return

        only_active = self._settings.get_boolean(["only_active_extruder"])

        for extruder_idx, sensors in self.sensors.items():
            # Skip disabled extruders
            if not self._settings.get_boolean([f"e{extruder_idx}_enabled"]):
                continue

            # Skip non-active extruders if configured
            if only_active and self.is_printing and extruder_idx != self.current_extruder:
                continue

            # Skip already triggered extruders during printing
            if self.is_printing and extruder_idx in self.triggered_extruders:
                continue

            try:
                # Read all GPIO pins at once (EasyMCP2221 returns tuple: gp0, gp1, gp2, gp3)
                gpio_readings = self.mcp.GPIO_read()

                # Extract individual sensor readings
                runout_sensor = sensors["runout"]
                motion_sensor = sensors["motion"]

                runout_reading = gpio_readings[runout_sensor.pin]
                motion_reading = gpio_readings[motion_sensor.pin]

                # Update sensor states
                runout_changed = runout_sensor.update(runout_reading)
                motion_changed = motion_sensor.update(motion_reading)

                # Check for triggers
                self._check_runout_trigger(extruder_idx, runout_sensor, runout_changed)
                self._check_motion_trigger(extruder_idx, motion_sensor)

                if self._settings.get_boolean(["debug_logging"]):
                    if runout_changed or motion_changed:
                        self._logger.debug(f"E{extruder_idx} sensors: runout={runout_sensor.last_stable_state}, "
                                        f"motion={motion_sensor.last_stable_state}")

            except Exception as e:
                self._logger.error(f"Error reading sensors for E{extruder_idx}: {e}")

    def _check_runout_trigger(self, extruder_idx: int, sensor: SensorState, state_changed: bool):
        """Check if runout sensor should trigger an action"""
        # Check if sensor is enabled for this extruder
        if not self._settings.get_boolean([f"e{extruder_idx}_enabled"]):
            return

        # Only trigger runout actions during printing
        if not self.is_printing:
            # Debug log to track why runouts might be happening when not printing
            if state_changed and not sensor.last_stable_state:
                self._logger.debug(
                    f"Runout detected on E{extruder_idx} but ignoring - not printing (is_printing={self.is_printing})"
                )
            return

        # Double-check printer state using OctoPrint's internal state
        if hasattr(self._printer, "is_printing") and not self._printer.is_printing():
            self._logger.debug(
                f"Runout detected on E{extruder_idx} but ignoring - printer not printing according to OctoPrint"
            )
            return

        # Trigger on runout (sensor goes from True to False, indicating no filament)
        if state_changed and not sensor.last_stable_state:
            self._logger.warning(
                f"Filament runout detected on E{extruder_idx} during active print"
            )
            self._trigger_runout_action(extruder_idx)

    def _check_motion_trigger(self, extruder_idx: int, sensor: SensorState):
        """Check if motion sensor should trigger due to timeout"""
        # Check if sensor is enabled for this extruder
        if not self._settings.get_boolean([f"e{extruder_idx}_enabled"]):
            return

        # Only trigger motion timeout actions during printing and not paused
        if not self.is_printing or self.print_paused:
            return

        timeout = self._settings.get_float([f"e{extruder_idx}_motion_timeout"])

        if sensor.get_motion_timeout_status(timeout):
            # Only trigger once per timeout event
            if time.time() - sensor.last_trigger_time > timeout:
                sensor.last_trigger_time = time.time()
                self._logger.warning(f"Motion timeout detected on E{extruder_idx} (no motion for {timeout}s)")
                self._trigger_motion_timeout_action(extruder_idx)

    def _trigger_runout_action(self, extruder_idx: int):
        """Execute actions when filament runout is detected"""
        self.triggered_extruders.add(extruder_idx)

        # Send notification
        if self._settings.get_boolean(["notification_enabled"]):
            self._plugin_manager.send_plugin_message(
                self._identifier,
                {
                    "type": "runout",
                    "extruder": extruder_idx,
                    "message": f"Filament runout detected on E{extruder_idx}"
                }
            )

        # Execute G-code commands
        runout_gcode = self._settings.get(["runout_gcode"]).strip()
        if runout_gcode:
            gcode_commands = [cmd.strip() for cmd in runout_gcode.split('\n') if cmd.strip()]

            for cmd in gcode_commands:
                if cmd.startswith('@'):
                    # OctoPrint action command
                    if cmd == '@pause':
                        self._printer.pause_print()
                elif cmd.startswith(';'):
                    # Comment - log it
                    self._logger.info(f"Runout action: {cmd}")
                else:
                    # Regular G-code
                    self._printer.commands(cmd)
                    self._logger.info(f"Sent runout G-code: {cmd}")
        else:
            # Fallback - just pause
            self._printer.pause_print()
            self._logger.info("No runout G-code configured, pausing print")

    def _trigger_motion_timeout_action(self, extruder_idx: int):
        """Execute actions when motion timeout is detected"""
        self.triggered_extruders.add(extruder_idx)

        # Send notification
        if self._settings.get_boolean(["notification_enabled"]):
            self._plugin_manager.send_plugin_message(
                self._identifier,
                {
                    "type": "motion_timeout",
                    "extruder": extruder_idx,
                    "message": f"Motion timeout detected on E{extruder_idx}"
                }
            )

        # Execute G-code commands
        motion_gcode = self._settings.get(["motion_timeout_gcode"]).strip()
        if motion_gcode:
            gcode_commands = [cmd.strip() for cmd in motion_gcode.split('\n') if cmd.strip()]

            for cmd in gcode_commands:
                if cmd.startswith('@'):
                    # OctoPrint action command
                    if cmd == '@pause':
                        self._printer.pause_print()
                elif cmd.startswith(';'):
                    # Comment - log it
                    self._logger.info(f"Motion timeout action: {cmd}")
                else:
                    # Regular G-code
                    self._printer.commands(cmd)
                    self._logger.info(f"Sent motion timeout G-code: {cmd}")
        else:
            # Fallback - just pause
            self._printer.pause_print()
            self._logger.info("No motion timeout G-code configured, pausing print")

    ##~~ Utility methods

    def get_update_information(self):
        """Software update hook"""
        return {
            "mcp2221_filament_sensor": {
                "displayName": "MCP2221A Filament Sensor",
                "displayVersion": self._plugin_version,
                "type": "github_release",
                "user": "chrisns",
                "repo": "OctoPrint-MCP2221-Filament-Sensor",
                "current": self._plugin_version,
                "stable_branch": {
                    "name": "Stable",
                    "branch": "main",
                    "comittish": ["main"],
                },
                "prerelease_branches": [
                    {
                        "name": "Release Candidate",
                        "branch": "rc",
                        "comittish": ["rc", "main"],
                    }
                ],
            }
        }
