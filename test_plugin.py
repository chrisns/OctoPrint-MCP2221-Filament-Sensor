#!/usr/bin/env python3
"""
Simple test script for the MCP2221A Filament Sensor Plugin
"""

import sys
import time
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_plugin_import():
    """Test if the plugin can be imported"""
    try:
        from octoprint_mcp2221_filament_sensor.mcp2221_filament_sensor import (
            MCP2221FilamentSensorPlugin, 
            SensorState, 
            MockMCP2221A
        )
        logger.info("✓ Plugin import successful")
        return True
    except ImportError as e:
        logger.error(f"✗ Plugin import failed: {e}")
        return False

def test_mock_hardware():
    """Test the mock hardware functionality"""
    try:
        from octoprint_mcp2221_filament_sensor.mcp2221_filament_sensor import MockMCP2221A
        
        mock = MockMCP2221A()
        
        # Test GPIO reading
        for pin in [0, 1, 2, 3]:
            value = mock.GPIO_read(pin)
            logger.info(f"✓ Mock GPIO pin {pin}: {value}")
            
        mock.close()
        logger.info("✓ Mock hardware test successful")
        return True
    except Exception as e:
        logger.error(f"✗ Mock hardware test failed: {e}")
        return False

def test_sensor_state():
    """Test SensorState functionality"""
    try:
        from octoprint_mcp2221_filament_sensor.mcp2221_filament_sensor import SensorState
        
        # Test runout sensor
        runout_sensor = SensorState(pin=0, sensor_type="runout", debounce_time=0.01)
        
        # Simulate state changes
        changed = runout_sensor.update(True)  # Filament present
        logger.info(f"✓ Runout sensor state: {runout_sensor.last_stable_state}")
        
        # Test motion sensor
        motion_sensor = SensorState(pin=1, sensor_type="motion", debounce_time=0.01)
        
        # Simulate motion pulses
        for i in range(5):
            motion_sensor.update(True)  # Pulse
            time.sleep(0.02)
            motion_sensor.update(False)
            time.sleep(0.02)
            
        rate = motion_sensor.get_motion_rate(window_seconds=1.0)
        logger.info(f"✓ Motion sensor rate: {rate:.1f} pulses/sec")
        
        # Test timeout
        timeout_status = motion_sensor.get_motion_timeout_status(0.1)
        logger.info(f"✓ Motion timeout status: {timeout_status}")
        
        logger.info("✓ SensorState test successful")
        return True
    except Exception as e:
        logger.error(f"✗ SensorState test failed: {e}")
        return False

def test_plugin_instantiation():
    """Test plugin instantiation"""
    try:
        from octoprint_mcp2221_filament_sensor.mcp2221_filament_sensor import MCP2221FilamentSensorPlugin
        
        plugin = MCP2221FilamentSensorPlugin()
        
        # Test settings defaults
        defaults = plugin.get_settings_defaults()
        logger.info(f"✓ Plugin settings defaults loaded: {len(defaults)} settings")
        
        # Test assets
        assets = plugin.get_assets()
        logger.info(f"✓ Plugin assets: {list(assets.keys())}")
        
        # Test templates
        templates = plugin.get_template_configs()
        logger.info(f"✓ Plugin templates: {len(templates)} templates")
        
        logger.info("✓ Plugin instantiation test successful")
        return True
    except Exception as e:
        logger.error(f"✗ Plugin instantiation test failed: {e}")
        return False

def main():
    """Run all tests"""
    logger.info("Starting MCP2221A Filament Sensor Plugin Tests...")
    
    tests = [
        test_plugin_import,
        test_mock_hardware,
        test_sensor_state,
        test_plugin_instantiation,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        logger.info(f"\nRunning {test.__name__}...")
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            logger.error(f"Test {test.__name__} crashed: {e}")
            failed += 1
    
    logger.info(f"\n=== Test Results ===")
    logger.info(f"Passed: {passed}")
    logger.info(f"Failed: {failed}")
    logger.info(f"Total:  {passed + failed}")
    
    if failed == 0:
        logger.info("✓ All tests passed!")
        return 0
    else:
        logger.error("✗ Some tests failed!")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 