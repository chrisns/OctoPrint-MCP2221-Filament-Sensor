# -*- coding: utf-8 -*-
########################################################################################################################

plugin_identifier = "mcp2221_filament_sensor"
plugin_package = "octoprint_mcp2221_filament_sensor"
plugin_name = "MCP2221A Filament Sensor"
plugin_version = "1.0.4"
plugin_description = """OctoPrint plugin for filament run-out and motion detection using MCP2221A USB-to-GPIO bridge. Supports dual extruders with independent sensor monitoring."""
plugin_author = "Chris Nesbitt-Smith"
plugin_author_email = "chris@nesbitt-smith.com"
plugin_url = "https://github.com/chrisns/OctoPrint-MCP2221-Filament-Sensor"
plugin_license = "MIT"

plugin_requires = [
    "EasyMCP2221>=1.4.0",
]

import setuptools

if __name__ == "__main__":
    setuptools.setup(
        name="OctoPrint-MCP2221-Filament-Sensor",
        version=plugin_version,
        description=plugin_description,
        long_description=plugin_description,
        long_description_content_type="text/plain",
        author=plugin_author,
        author_email=plugin_author_email,
        url=plugin_url,
        license=plugin_license,
        install_requires=plugin_requires,
        additional_requirements=dict(
            develop=[
                "pytest>=6.0.0",
                "pytest-mock>=3.0.0",
            ]
        ),
        
        packages=setuptools.find_packages(),
        include_package_data=True,
        package_data={
            # If any package contains *.txt or *.rst files, include them:
            "": ["*.txt", "*.rst", "*.md"],
            # Include HTML templates and JavaScript files
            plugin_package: [
                "templates/*.jinja2",
                "static/js/*.js",
                "static/css/*.css",
            ],
        },
        
        zip_safe=False,
        
        entry_points={
            "octoprint.plugin": [
                f"{plugin_identifier} = {plugin_package}"
            ]
        },
        
        python_requires=">=3.7",
        classifiers=[
            "Development Status :: 4 - Beta",
            "Intended Audience :: Developers",
            "License :: OSI Approved :: MIT License",
            "Programming Language :: Python :: 3",
            "Programming Language :: Python :: 3.7",
            "Programming Language :: Python :: 3.8",
            "Programming Language :: Python :: 3.9",
            "Programming Language :: Python :: 3.10",
            "Programming Language :: Python :: 3.11",
        ],
    ) 
