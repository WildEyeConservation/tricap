"""D Joubert 18 November 2016 - Configurator - handles reading and saving the initial config."""

import configparser
import logging
import os

from config import (
    CONFIG_FP,
    DEFAULT_CONFIG_FP,
    SONY_IMAGE_FORMAT_CAMERA_SETTING,
    SONY_IMAGE_FORMAT_CONFIG_KEY,
)


class TricapConfigError(Exception):
    pass


class TricapConfig:
    """TricapConfig: Object that reads and writes settings from/to a config file, handling the
    translation from machine code to human readable format, and back again. Uses the
    configparser to do most of the heavy lifting.
    - Options are layered: default.cfg (shipped with the code) lists every supported option,
      and initial.cfg (on the device) overrides any of them. Reads see the merged view.
    - Saving writes only the options the UI manages back to initial.cfg, so a rig's own
      overrides are kept and default.cfg keeps its comments.
    - Note that keys in sections are case-insensitive and stored in lowercase, and that all keys
      in sections are accessible in a case-insensitive manner.
    - The TricapConfig is treated as a flight critical component, and therefore any exceptions
      raised should be raised, i.e. the system should halt and catch fire. A missing
      initial.cfg is the one exception: the defaults are complete, so it is simply created on
      the first save.
    """

    _logger = logging.getLogger(__name__)

    CAMERA_SECTION_HEADER = "Camera"
    MISC_SECTION_HEADER = "Misc"
    UI_SECTION_HEADER = "Ui"

    # Options the UI changes at runtime; the only ones written back to initial.cfg.
    PERSISTED_OPTIONS = {
        CAMERA_SECTION_HEADER: (SONY_IMAGE_FORMAT_CONFIG_KEY,),
        MISC_SECTION_HEADER: ("image_capture_interval",),
    }

    # Sections and options that older initial.cfg files may still carry but nothing reads.
    RETIRED_SECTIONS = ("Web", "SMS", "Altimeter")
    RETIRED_MISC_OPTIONS = ("session_description",)

    # Lowest accepted value per [Ui] option; anything faster hammers the rig over Wi-Fi.
    UI_MINIMUMS_MS = {
        "status_poll_ms": 250,
        "sensors_poll_ms": 250,
        "sensors_poll_capturing_ms": 250,
        "background_poll_ms": 1000,
        "uplink_poll_ms": 1000,
        "netbird_poll_ms": 1000,
        "backup_poll_ms": 250,
        "verify_poll_ms": 250,
        "heartbeat_ms": 1000,
    }

    TYPE_STRING = "string"
    TYPE_INT = "int"
    TYPE_FLOAT = "float"

    def __init__(self, config_fp_to_read=CONFIG_FP, defaults_fp=DEFAULT_CONFIG_FP):
        self._parser = self._new_parser()
        self._overrides = self._new_parser()

        self._config_fp = config_fp_to_read
        self._defaults_fp = defaults_fp
        self._ready_flag = False

        try:
            # read_file (rather than read) makes the parser raise on a problem with the file
            with open(self._defaults_fp) as defaults_file:
                self._parser.read_file(defaults_file)
            if os.path.exists(self._config_fp):
                with open(self._config_fp) as config_file:
                    self._overrides.read_file(config_file)
            else:
                self._logger.info("No %s yet; running on default.cfg alone", self._config_fp)
            self._retire_legacy_options(self._overrides)
            for section in self._overrides.sections():
                if not self._parser.has_section(section):
                    self._parser.add_section(section)
                for key, value in self._overrides.items(section, raw=True):
                    self._parser.set(section, key, value)
            self._ready_flag = True
        except (configparser.Error, OSError) as ex:
            self._logger.error("Error reading config files %s and %s", self._defaults_fp, self._config_fp)
            self._logger.error("configparser exception: %s", ex.args)
            # If there is an error reading from the config file, the system should fall over
            raise

    @staticmethod
    def _new_parser():
        return configparser.ConfigParser(inline_comment_prefixes=(";",))

    def _retire_legacy_options(self, parser):
        """Drop options from an older initial.cfg that nothing reads any more."""
        for retired_section in self.RETIRED_SECTIONS:
            parser.remove_section(retired_section)
        if parser.has_section(self.MISC_SECTION_HEADER):
            for retired_option in self.RETIRED_MISC_OPTIONS:
                parser.remove_option(self.MISC_SECTION_HEADER, retired_option)
        if parser.has_section(self.CAMERA_SECTION_HEADER):
            for option in tuple(parser.options(self.CAMERA_SECTION_HEADER)):
                if option != SONY_IMAGE_FORMAT_CONFIG_KEY:
                    parser.remove_option(self.CAMERA_SECTION_HEADER, option)
            # The pre-SDK name for leaving the camera body's own format alone.
            if parser.get(self.CAMERA_SECTION_HEADER, SONY_IMAGE_FORMAT_CONFIG_KEY, fallback=None) == "Camera setting":
                parser.set(self.CAMERA_SECTION_HEADER, SONY_IMAGE_FORMAT_CONFIG_KEY, SONY_IMAGE_FORMAT_CAMERA_SETTING)

    def is_ready(self):
        return self._ready_flag

    def get_section_dict(self, section_header):
        """Get all the parameters for a particular section"""

        assert self._ready_flag

        try:
            items = self._parser.items(section_header)
        except configparser.Error as ex:
            self._logger.error(ex)
            raise

        return dict(items)

    def get(self, id_str, section_header, type_str="string"):

        assert self._ready_flag

        try:
            val_str = self._parser[section_header][id_str]
        except (OSError, configparser.Error, KeyError) as ex:
            self._logger.error("Error reading from config file %s", self._config_fp)
            self._logger.error(ex)
            raise

        ret_val = val_str
        try:
            if type_str == TricapConfig.TYPE_INT:
                ret_val = int(val_str)
            elif type_str == TricapConfig.TYPE_FLOAT:
                ret_val = float(val_str)
        except ValueError:
            self._logger.error("Error converting string %s to %s", val_str, type_str)
            raise

        return ret_val

    def ui_settings(self):
        """The [Ui] section as validated integers, keyed as in default.cfg."""

        assert self._ready_flag

        settings = {}
        for key, minimum in self.UI_MINIMUMS_MS.items():
            value = int(self.get(key, self.UI_SECTION_HEADER, self.TYPE_INT))
            if value < minimum:
                self._logger.error("[Ui] %s = %s is below the minimum of %s ms", key, value, minimum)
                raise TricapConfigError(f"[Ui] {key} must be at least {minimum} ms, got {value}")
            settings[key] = value
        return settings

    def set_section(self, section_dict: dict, section_header):
        """Change the values stored in the internal configparser.

        Note that settings will only be changed. Nothing gets added or removed.
        """
        # Using an assert, because this should really not happen
        assert self._ready_flag

        key = None
        try:
            for key in section_dict.keys():
                if key not in self._parser[section_header]:
                    self._logger.warning("Not setting %s, which was not in the original cfg", key)
                    raise TricapConfigError
                else:
                    self._parser.set(section_header, key, str(section_dict[key]))
        except (configparser.Error, KeyError) as ex:
            self._logger.error("Error setting %s as %s in section %s", key, section_dict.get(key), section_header)
            self._logger.error("configparser exception: %s", ex.args)
            raise

    def save_to_file(self, config_fp=None):
        """Write the UI-managed options to initial.cfg, keeping the rig's other overrides."""

        assert self._ready_flag

        if config_fp is None:
            config_fp = self._config_fp

        for section, options in self.PERSISTED_OPTIONS.items():
            if not self._overrides.has_section(section):
                self._overrides.add_section(section)
            for option in options:
                self._overrides.set(section, option, self._parser.get(section, option, raw=True))

        try:
            with open(config_fp, "w") as config_file:
                self._overrides.write(config_file)
        except (OSError, configparser.Error) as ex:
            self._logger.error("Error writing configs to file %s", config_fp)
            self._logger.error(ex)
            raise
