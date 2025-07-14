# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

import octoprint.plugin

__plugin_name__ = "MCP2221A Filament Sensor"
__plugin_pythoncompat__ = ">=3.7,<4"

def __plugin_load__():
    global __plugin_implementation__
    global __plugin_hooks__
    
    from .mcp2221_filament_sensor import MCP2221FilamentSensorPlugin
    
    __plugin_implementation__ = MCP2221FilamentSensorPlugin()
    
    __plugin_hooks__ = {
        "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information,
    } 