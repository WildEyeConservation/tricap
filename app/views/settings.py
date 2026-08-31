"""The settings page is built on the following assumptions.

The are only three types of settings: camera, alti, miscellaneous.
If a setting is not in the initial.cfg file, it is not displayed or made modifiable
"""

from flask import Blueprint, redirect, url_for, render_template, request

from app import forms, tricap_manager, altimeter, session_logger
from config import DEFAULT_CONFIG_FP, CONFIG_FP
from support.configure import TricapConfig
from collections import namedtuple
from collections import OrderedDict

from app import rootlogger

settings_bp = Blueprint('settings', __name__)


class MiscSettingConfig:
    Accessors = namedtuple('Accessors', 'getter setter')

    _settings = {'session_description': Accessors(getter=session_logger.get_description,
                                                  setter=session_logger.set_description),
                 'image_capture_interval': Accessors(getter=tricap_manager.get_image_capture_interval,
                                                     setter=tricap_manager.set_image_capture_interval)}

    def __repr__(self):
        return str(self._settings.keys())

    def __dir__(self):
        return self._settings.keys()

    def __setattr__(self, key, value):
        self._settings[key].setter(value)

    def __getattr__(self, key):
        return self._settings[key].getter()

    __setitem__ = __setattr__
    __getitem__ = __getattr__


class MiscSettingHandler:
    """ Handles all the settings which are not applicable to the sensors. To keep in line with
        how the TricapConfig handles things, all variables are returned as strings """

    def __init__(self):
        self._setting_strings = ['session_description', 'image_capture_interval']

    @property
    def config(self):
        return MiscSettingConfig()


class WebSettingHandler:
    """Handlers all settings to do with the web interface. Currently, just a dict."""
    def __init__(self, config):
        """Constructor."""
        self.config = config


# TODO SMS Settings Handler should get its settings from the actual sms objects
class SMSSettingHandler:
    """Handles all settings to do with the SMS interface (just a dictionary at the moment)."""
    def __init__(self, config):
        """Constructor."""
        self.config = config


def populate_form_section(sdict, handler, form_selects, form_strings, set_data=True):
    """Populate the settings section of the form."""
    for key in sdict.keys():
        # check if its a select
        try:
            choices = handler.config[key].choices
        except AttributeError:
            choices = None
        if choices is not None and len(choices) != 0:
            choices_tuples = []
            for index, choice in enumerate(choices):
                choices_tuples.append((str(index), choice))

            form_selects.append_entry()
            form_selects[-1].label = key
            form_selects[-1].choices = choices_tuples

            if set_data is True:
                config_val = tricap_manager.config[key]
                if config_val is not None:
                    form_selects[-1].data = str(choices.index(config_val))
        else:
            form_strings.append_entry()
            form_strings[-1].label = key
            if set_data is True:
                config_val = handler.config[key]
                if config_val is not None:
                    form_strings[-1].data = config_val


def get_form_for_display(config_fp=CONFIG_FP, set_data=True):
    """ Returns a SettingsForm populated with values from the setting sources as per the config
    file. Current settings need to be checked, so that if something was not set during the overall
    init, we could pick it up here (or if we are just testing a new setting something)"""

    config = TricapConfig(config_fp_to_read=config_fp)
    # Specify the form data as None to prevent automatic population with the request.Form data.
    # The request form data does not contain the label and choice information.
    form = forms.SettingsForm(formdata=None)

    # Populate the form
    cam_dict = config.get_section_dict(TricapConfig.CAMERA_SECTION_HEADER)
    cam_dict = OrderedDict(sorted(cam_dict.items(), key=lambda t: t[0]))
    #cam_dict = dict(sorted(cam_dict.items()))
    populate_form_section(cam_dict, tricap_manager, form.cam_selects, form.cam_strings, set_data)

    alti_dict = config.get_section_dict(TricapConfig.ALTI_SECTION_HEADER)
    alti_dict = OrderedDict(sorted(alti_dict.items(), key=lambda t: t[0]))
    #alti_dict = dict(sorted(alti_dict.items()))
    populate_form_section(alti_dict, altimeter, form.alti_selects, form.alti_strings, set_data)

    misc_setting_handler = MiscSettingHandler()
    misc_dict = config.get_section_dict(TricapConfig.MISC_SECTION_HEADER)
    misc_dict = OrderedDict(sorted(misc_dict.items(), key=lambda t: t[0]))
    #misc_dict = dict(sorted(misc_dict.items()))
    populate_form_section(misc_dict, misc_setting_handler, form.misc_selects, form.misc_strings,
                          set_data)

    web_dict = config.get_section_dict(TricapConfig.WEB_SECTION_HEADER)
    web_dict = OrderedDict(sorted(web_dict.items(), key=lambda t: t[0]))
    #web_dict = dict(sorted(web_dict.items()))
    web_setting_handler = WebSettingHandler(web_dict)
    populate_form_section(web_dict, web_setting_handler, form.web_selects, form.web_strings,
                          set_data)

    sms_dict = config.get_section_dict(TricapConfig.SMS_SECTION_HEADER)
    sms_dict = OrderedDict(sorted(sms_dict.items(), key=lambda t: t[0]))
    #sms_dict = dict(sorted(sms_dict.items()))
    sms_setting_handler = SMSSettingHandler(sms_dict)
    populate_form_section(sms_dict, sms_setting_handler, form.sms_selects, form.sms_strings,
                          set_data)

    return form


def populate_pushed_form_section(pf_strings, pf_selects, df_strings, df_selects):
    """Populate the form."""
    for index in range(len(df_strings)):
        pf_strings[index].label = df_strings[index].label

    for index in range(len(df_selects)):
        pf_selects[index].label = df_selects[index].label
        pf_selects[index].choices = df_selects[index].choices


def populate_pushed_form(pushed_form):
    """ for some reason, the pushed form loses the labels of the added fields, so have to add em"""
    display_form = get_form_for_display(set_data=False)

    populate_pushed_form_section(pushed_form.cam_strings, pushed_form.cam_selects,
                                 display_form.cam_strings, display_form.cam_selects)

    populate_pushed_form_section(pushed_form.alti_strings, pushed_form.alti_selects,
                                 display_form.alti_strings, display_form.alti_selects)

    populate_pushed_form_section(pushed_form.misc_strings, pushed_form.misc_selects,
                                 display_form.misc_strings, display_form.misc_selects)

    populate_pushed_form_section(pushed_form.web_strings, pushed_form.web_selects,
                                 display_form.web_strings, display_form.web_selects)

    populate_pushed_form_section(pushed_form.sms_strings, pushed_form.sms_selects,
                                 display_form.sms_strings, display_form.sms_selects)

    return pushed_form


def extract_dict_info_from_form_section(section_dict, form_strings, form_selects):
    for index in range(len(form_strings)):
        # Replacing the %20 introducted by the HTML Form when there is a space in a string, because
        #  the configparser uses % to indicate values which should be interpolated.
        section_dict[form_strings[index].label] = form_strings[index].data.replace('%20', ' ')

    for index in range(len(form_selects)):
        choices = [ct[1] for ct in form_selects[index].choices]
        section_dict[form_selects[index].label] = choices[int(form_selects[index].data)]


def convert_populated_form_to_dict(form):
    form_dict = {TricapConfig.CAMERA_SECTION_HEADER: {}, TricapConfig.ALTI_SECTION_HEADER: {},
                 TricapConfig.MISC_SECTION_HEADER: {}, TricapConfig.WEB_SECTION_HEADER: {},
                 TricapConfig.SMS_SECTION_HEADER: {}}

    extract_dict_info_from_form_section(form_dict[TricapConfig.CAMERA_SECTION_HEADER],
                                        form.cam_strings, form.cam_selects)

    form_dict[TricapConfig.ALTI_SECTION_HEADER] = {}
    extract_dict_info_from_form_section(form_dict[TricapConfig.ALTI_SECTION_HEADER],
                                        form.alti_strings, form.alti_selects)

    form_dict[TricapConfig.MISC_SECTION_HEADER] = {}
    extract_dict_info_from_form_section(form_dict[TricapConfig.MISC_SECTION_HEADER],
                                        form.misc_strings, form.misc_selects)

    form_dict[TricapConfig.WEB_SECTION_HEADER] = {}
    extract_dict_info_from_form_section(form_dict[TricapConfig.WEB_SECTION_HEADER],
                                        form.web_strings, form.web_selects)

    form_dict[TricapConfig.SMS_SECTION_HEADER] = {}
    extract_dict_info_from_form_section(form_dict[TricapConfig.SMS_SECTION_HEADER],
                                        form.sms_strings, form.sms_selects)

    return form_dict


def set_setting_handler_with_dict(handler, sdict):
    for key, value in sdict.items():
        handler.config[key] = value


def change_settings(form):
    form_dict = convert_populated_form_to_dict(form)

    set_setting_handler_with_dict(tricap_manager, form_dict[TricapConfig.CAMERA_SECTION_HEADER])
    set_setting_handler_with_dict(altimeter, form_dict[TricapConfig.ALTI_SECTION_HEADER])

    misc_setting_handler = MiscSettingHandler()
    set_setting_handler_with_dict(misc_setting_handler, form_dict[TricapConfig.MISC_SECTION_HEADER])

    config = TricapConfig()
    web_dict = config.get_section_dict(TricapConfig.WEB_SECTION_HEADER)
    web_setting_handler = WebSettingHandler(web_dict)
    set_setting_handler_with_dict(web_setting_handler, form_dict[TricapConfig.WEB_SECTION_HEADER])

    config = TricapConfig()
    sms_dict = config.get_section_dict(TricapConfig.SMS_SECTION_HEADER)
    sms_setting_handler = SMSSettingHandler(sms_dict)
    set_setting_handler_with_dict(sms_setting_handler, form_dict[TricapConfig.SMS_SECTION_HEADER])


def save_settings(form, config_fp=CONFIG_FP):
    # get the current settings in a dict
    config = TricapConfig(config_fp_to_read=config_fp)

    # modify the settings dict based on settings in the form (i.e. the user selected options)
    form_dict = convert_populated_form_to_dict(form)

    for section_header in TricapConfig.SECTION_HEADERS:
        config.set_section(form_dict[section_header], section_header)

    config.save_to_file()


def revert_to_default_settings(save_to_fp=CONFIG_FP):
    """Copy the default settings file over the current used one."""
    default_config = TricapConfig(config_fp_to_read=DEFAULT_CONFIG_FP)
    config = TricapConfig(config_fp_to_read=save_to_fp)

    for section_header in TricapConfig.SECTION_HEADERS:
        config.set_section(default_config.get_section_dict(section_header), section_header)

    config.save_to_file()


@settings_bp.route('/setup', methods=['GET', 'POST'])
@settings_bp.route('/settings', methods=['GET', 'POST'])
def settings():
    rootlogger.info('Settings Page Requested.')
    if request.path == '/setup' and request.method == 'GET':
        return render_template('/settings/settings.html', form=None)
    if request.method == 'GET':
        # When the user initially opens the page, we need to setup the choices and labels for the
        #  forms
        form = get_form_for_display()
    else:
        # When the users posts (i.e. clicks one of the submit buttons), any SettingsForm will be
        #  populated with the data from the request.form (i.e. from the browser). However, this form
        #  does not contain the labels and choices of the FieldLists, so we need to populate those
        #  attributes.
        # TODO Find out why the labels and choices are missing from the FieldLists
        form = populate_pushed_form(forms.SettingsForm())

    if form.validate_on_submit():
        # tricap_manager.stop_capturing()
        # altimeter.stop_measuring()

        # if form.test.data is True:
        #     change_settings(form)
        if form.save.data is True:
            change_settings(form)
            save_settings(form)
        elif form.revert.data is True:
            revert_to_default_settings()

        return redirect(url_for('home.index'))  # return back to home once settinsg are changed

    return render_template('/settings/settings.html', form=form)
