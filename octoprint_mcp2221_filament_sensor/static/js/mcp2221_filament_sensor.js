/*
 * View model for MCP2221A Filament Sensor Plugin
 */
$(function() {
    function MCP2221FilamentSensorViewModel(parameters) {
        var self = this;

        self.settings = parameters[0];
        self.loginState = parameters[1];

        // Observable properties
        self.sensorStatus = ko.observable();
        self.testResults = ko.observable();
        self.testingInProgress = ko.observable(false);

        // Auto-refresh status every 5 seconds
        self.statusUpdateInterval = null;

        self.onBeforeBinding = function() {
            // Start status updates when settings page is opened
            self.startStatusUpdates();
        };

        self.onAfterBinding = function() {
            // Additional setup if needed
        };

        self.onSettingsShown = function() {
            self.startStatusUpdates();
        };

        self.onSettingsHidden = function() {
            self.stopStatusUpdates();
        };

        // Start automatic status updates
        self.startStatusUpdates = function() {
            if (self.statusUpdateInterval) {
                clearInterval(self.statusUpdateInterval);
            }
            
            // Update immediately
            self.updateStatus();
            
            // Then update every 5 seconds
            self.statusUpdateInterval = setInterval(function() {
                self.updateStatus();
            }, 5000);
        };

        // Stop automatic status updates
        self.stopStatusUpdates = function() {
            if (self.statusUpdateInterval) {
                clearInterval(self.statusUpdateInterval);
                self.statusUpdateInterval = null;
            }
        };

        // Update sensor status
        self.updateStatus = function() {
            if (!self.loginState.loggedIn()) {
                return;
            }

            $.ajax({
                url: API_BASEURL + "plugin/mcp2221_filament_sensor",
                type: "GET",
                dataType: "json",
                success: function(response) {
                    self.sensorStatus(response);
                },
                error: function(jqXHR, textStatus, errorThrown) {
                    console.error("Failed to get sensor status:", textStatus, errorThrown);
                    self.sensorStatus(null);
                }
            });
        };

        // Test sensors
        self.testSensors = function() {
            console.log("Test sensors button clicked");

            if (!self.loginState.loggedIn()) {
              console.log("User not logged in, cannot test sensors");
              return;
            }

            self.testingInProgress(true);
            self.testResults("");

            console.log("Sending test_sensors request...");

            $.ajax({
              url: API_BASEURL + "plugin/mcp2221_filament_sensor",
              type: "POST",
              dataType: "json",
              data: JSON.stringify({
                command: "test_sensors",
              }),
              contentType: "application/json; charset=utf-8",
              success: function (response) {
                console.log("Test sensors response received:", response);
                self.testingInProgress(false);

                // Format the results for display
                var formatted = "Sensor Test Results:\n\n";

                if (response.e0) {
                  formatted += "Extruder 0:\n";
                  if (response.e0.error) {
                    formatted += "  Error: " + response.e0.error + "\n";
                  } else {
                    formatted +=
                      "  Runout Sensor (Pin " +
                      response.e0.runout.pin +
                      "): " +
                      (response.e0.runout.raw_value ? "HIGH" : "LOW") +
                      "\n";
                    formatted +=
                      "  Motion Sensor (Pin " +
                      response.e0.motion.pin +
                      "): " +
                      (response.e0.motion.raw_value ? "HIGH" : "LOW") +
                      "\n";
                  }
                  formatted += "\n";
                }

                if (response.e1) {
                  formatted += "Extruder 1:\n";
                  if (response.e1.error) {
                    formatted += "  Error: " + response.e1.error + "\n";
                  } else {
                    formatted +=
                      "  Runout Sensor (Pin " +
                      response.e1.runout.pin +
                      "): " +
                      (response.e1.runout.raw_value ? "HIGH" : "LOW") +
                      "\n";
                    formatted +=
                      "  Motion Sensor (Pin " +
                      response.e1.motion.pin +
                      "): " +
                      (response.e1.motion.raw_value ? "HIGH" : "LOW") +
                      "\n";
                  }
                }

                // Handle case where no extruders are enabled
                if (!response.e0 && !response.e1) {
                  formatted += "No extruders enabled or hardware error.\n";
                  if (response.error) {
                    formatted += "Error: " + response.error + "\n";
                  }
                }

                console.log("Setting test results:", formatted);
                self.testResults(formatted);
              },
              error: function (jqXHR, textStatus, errorThrown) {
                console.log(
                  "Test sensors request failed:",
                  jqXHR,
                  textStatus,
                  errorThrown
                );
                self.testingInProgress(false);

                var errorMsg = "Sensor test failed: ";
                if (jqXHR.responseJSON && jqXHR.responseJSON.error) {
                  errorMsg += jqXHR.responseJSON.error;
                } else if (jqXHR.responseText) {
                  errorMsg += jqXHR.responseText;
                } else {
                  errorMsg += textStatus + " - " + errorThrown;
                }

                console.log("Setting error message:", errorMsg);
                self.testResults(errorMsg);
              },
            });
        };

        // Handle plugin messages
        self.onDataUpdaterPluginMessage = function(plugin, data) {
            if (plugin !== "mcp2221_filament_sensor") {
                return;
            }

            // Show notifications for sensor triggers
            if (data.type === "runout") {
                new PNotify({
                    title: "Filament Runout",
                    text: data.message,
                    type: "error",
                    hide: false
                });
            } else if (data.type === "motion_timeout") {
                new PNotify({
                    title: "Motion Timeout",
                    text: data.message,
                    type: "warning",
                    hide: false
                });
            }
        };

        // Clean up on destroy
        self.onDestroy = function() {
            self.stopStatusUpdates();
        };
    }

    // Register the view model
    OCTOPRINT_VIEWMODELS.push({
        construct: MCP2221FilamentSensorViewModel,
        dependencies: ["settingsViewModel", "loginStateViewModel"],
        elements: ["#settings_plugin_mcp2221_filament_sensor"]
    });
}); 