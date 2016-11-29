""" The settings page is built on the following assumptions:
    - The are only three types of settings: camera, alti, miscellaneous.
    - If a setting is not in the initial.cfg file, it is not displayed or made modifiable
"""

import pdb

from flask import Blueprint, render_template, request, redirect, url_for
from flask import current_app

from app import forms, tricap_manager, altimeter, session_logger
from sensors.configure import TricapConfig

from config import DEFAULT_CONFIG_FP, CONFIG_FP, RET_OK, RET_ERROR

settings_bp = Blueprint('settings', __name__)



class MiscSettingHandler():
    """ Handles all the settings which are not applicable to the sensors """
    def __init__(self):
        self._setting_strings = ['session_description', 'image_capture_interval']

    def set_setting(self, setting_str, val_str):
        if setting_str in self._setting_strings:
            if setting_str == 'session_description':
                return session_logger.set_description(val_str)
            elif setting_str == 'image_capture_interval':
                return tricap_manager.set_setting('image_capture_interval', val_str)
        else:
            return RET_ERROR

        return RET_OK

    def get_setting(self, setting_str):
        ret_val = None

        if setting_str in self._setting_strings:
            if setting_str == 'session_description':
                ret_val = session_logger.get_description()
            elif setting_str == 'image_capture_interval':
                ret_val = tricap_manager.get_image_capture_interval()

        return ret_val

# TODO This got out of hand, should definitely be able to make this simplified

def get_form_for_display(config_fp = CONFIG_FP, set_data=True):
    """ Returns a SettingsForm populated with values from the setting sources as per the config
    file. Current settings need to be checked, so that if something was not set during the overall
    init, we could pick it up here (or if we are just testing a new setting something)"""

    config = TricapConfig(config_fp_to_read=config_fp)
    # Specify the form data as None to prevent automatic population with the request.Form data.
    # The request form data does not contain the label and choice information.
    form = forms.SettingsForm(formdata=None)

    # TODO Clean this up by having the tricap_manager, altimeter and misc_handler inherit from a
    #   setting source abstract base class (can you do multiple inheritance?)

    # Populate the form
    cam_dict = config.get_section_dict(TricapConfig.CAMERA_SECTION_HEADER)
    for key in cam_dict.keys():
        # check if its a select
        choices = tricap_manager.get_choices_for_setting(key)
        if choices is not None and len(choices) != 0:
            choices_tuples = []
            for index, choice in enumerate(choices):
                choices_tuples.append((str(index), choice))

            form.cam_selects.append_entry()
            form.cam_selects[-1].label = key
            form.cam_selects[-1].choices = choices_tuples

            if set_data is True:
                config_val = tricap_manager.get_setting(key)
                if config_val is not None:
                    form.cam_selects[-1].data = str(choices.index(config_val))
        else:
            form.cam_strings.append_entry()
            form.cam_strings[-1].label = key
            if set_data is True:
                config_val = tricap_manager.get_setting(key)
                if config_val is not None:
                    form.cam_strings[-1].data = config_val

    # Get those settings pertaining to the altimeter
    # TODO I'm cheating here, knowing that the alti only has string settings
    alti_dict = config.get_section_dict(TricapConfig.ALTI_SECTION_HEADER)
    for key in alti_dict:
        form.alti_strings.append_entry()
        form.alti_strings[-1].label = key
        if set_data is True:
            config_val = altimeter.get_setting(key)
            if config_val is not None:
                form.alti_strings[-1].data = config_val

    # Get those settings pertaining to the misc
    # TODO Again, I cheat, knowing that misc only has string settings
    misc_setting_handler = MiscSettingHandler()
    misc_dict = config.get_section_dict(TricapConfig.MISC_SECTION_HEADER)
    for key in misc_dict:
        form.misc_strings.append_entry()
        form.misc_strings[-1].label = key
        if set_data is True:
            config_val = misc_setting_handler.get_setting(key)
            if config_val is not None:
                form.misc_strings[-1].data = config_val

    return form

def populate_pushed_form(pushed_form):
    """ for some reason, the pushed form loses the labels of the added fields, so have to add em"""
    display_form = get_form_for_display(set_data=False)

    for index in range(len(display_form.cam_strings)):
        pushed_form.cam_strings[index].label = display_form.cam_strings[index].label

    for index in range(len(display_form.cam_selects)):
        pushed_form.cam_selects[index].label = display_form.cam_selects[index].label
        pushed_form.cam_selects[index].choices = display_form.cam_selects[index].choices

    for index in range(len(display_form.alti_strings)):
        pushed_form.alti_strings[index].label = display_form.alti_strings[index].label

    for index in range(len(display_form.alti_selects)):
        pushed_form.alti_selects[index].label = display_form.alti_selects[index].label
        pushed_form.alti_selects[index].choices = display_form.alti_selects[index].choices

    for index in range(len(display_form.misc_strings)):
        pushed_form.misc_strings[index].label = display_form.misc_strings[index].label

    for index in range(len(display_form.misc_selects)):
        pushed_form.misc_selects[index].label = display_form.misc_selects[index].label
        pushed_form.misc_selects[index].choices = display_form.misc_selects[index].choices

    return pushed_form

def convert_populated_form_to_dict(form):
    form_dict = {}

    sh = TricapConfig.CAMERA_SECTION_HEADER
    form_dict[sh] = {}
    for index in range(len(form.cam_strings)):
        form_dict[sh][form.cam_strings[index].label] = form.cam_strings[index].data.replace('%20', ' ')

    for index in range(len(form.cam_selects)):
        choices = [ct[1] for ct in form.cam_selects[index].choices]
        form_dict[sh][form.cam_selects[index].label] = choices[int(form.cam_selects[index].data)]

    sh = TricapConfig.ALTI_SECTION_HEADER
    form_dict[sh] = {}
    for index in range(len(form.alti_strings)):
        form_dict[sh][form.alti_strings[index].label] = form.alti_strings[index].data.replace('%20', ' ')

    for index in range(len(form.alti_selects)):
        choices = [ct[1] for ct in form.alti_selects[index].choices]
        form_dict[sh][form.alti_selects[index].label] = choices[int(form.alti_selects[index].data)]

    sh = TricapConfig.MISC_SECTION_HEADER
    form_dict[sh] = {}
    for index in range(len(form.misc_strings)):
        form_dict[sh][form.misc_strings[index].label] = form.misc_strings[index].data.replace('%20', ' ')

    for index in range(len(form.misc_selects)):
        choices = [ct[1] for ct in form.misc_selects[index].choices]
        form_dict[sh][form.misc_selects[index].label] = choices[int(form.misc_selects[index].data)]

    return form_dict

def set_setting_sink_with_dict(sink, sdict):
    # TODO Should we do this here, how should we handle the returns? Figure it out on merging
    ret_val = 0
    for key in sdict.keys():
        ret_val += sink.set_setting(key, sdict[key])

    return ret_val

def change_settings(form):
    form_dict = convert_populated_form_to_dict(form)

    set_setting_sink_with_dict(tricap_manager, form_dict[TricapConfig.CAMERA_SECTION_HEADER])
    set_setting_sink_with_dict(altimeter, form_dict[TricapConfig.ALTI_SECTION_HEADER])

    misc_setting_handler = MiscSettingHandler()
    set_setting_sink_with_dict(misc_setting_handler, form_dict[TricapConfig.MISC_SECTION_HEADER])

def save_settings(form, config_fp=CONFIG_FP, logger=None):

    # If no logger is specified, use the apps logger (having it as default
    #  freaks out the app initialisation)
    if logger is None:
        logger = current_app.logger

    # get the current settings in a dict
    config = TricapConfig(config_fp_to_read=config_fp)

    # modify the settings dict based on settings in the form (i.e. the user selected options)
    form_dict = convert_populated_form_to_dict(form)

    config.set_section(form_dict[TricapConfig.CAMERA_SECTION_HEADER],
                                 TricapConfig.CAMERA_SECTION_HEADER)
    config.set_section(form_dict[TricapConfig.ALTI_SECTION_HEADER],
                                 TricapConfig.ALTI_SECTION_HEADER)
    config.set_section(form_dict[TricapConfig.MISC_SECTION_HEADER],
                                 TricapConfig.MISC_SECTION_HEADER)

    config.save_to_file()

def revert_to_default_settings(save_to_fp=CONFIG_FP, logger=None):
    # arguments are only supposed to be used during unittesting
    if logger is None:
        logger = current_app.logger

    default_config = TricapConfig(config_fp_to_read=DEFAULT_CONFIG_FP)
    config = TricapConfig(config_fp_to_read=save_to_fp)
    # config.clear_config()
    config.set_section(default_config.get_section_dict(TricapConfig.CAMERA_SECTION_HEADER),
                       TricapConfig.CAMERA_SECTION_HEADER)
    config.set_section(default_config.get_section_dict(TricapConfig.ALTI_SECTION_HEADER),
                       TricapConfig.ALTI_SECTION_HEADER)
    config.set_section(default_config.get_section_dict(TricapConfig.MISC_SECTION_HEADER),
                       TricapConfig.MISC_SECTION_HEADER)
    config.save_to_file()

@settings_bp.route('/settings', methods=['GET', 'POST'])
def settings():

    if request.method == 'GET':
        # When the user initially opens the page, we need to setup the choices and labels for the
        #  forms
        form = get_form_for_display()
    else:
        # When the users posts (i.e. clicks one of the submit buttons), any SettingsForm will be
        #  populated with the data from the request.form (i.e. from the browser). However, this form
        #  does not contain the labels and choices of the FieldLists, so we need to populate those
        #  attributes.
        # TODO Find out why the lables and choices are missing from the FieldLists
        form = populate_pushed_form(forms.SettingsForm())

    if form.validate_on_submit():
        tricap_manager.stop_capturing()
        altimeter.stop_measuring()

        if form.test.data is True:
            change_settings(form)
        elif form.save.data is True:
            change_settings(form)
            save_settings(form)
        elif form.revert.data is True:
            revert_to_default_settings()

        return redirect(url_for('home.index'))

    return render_template('/settings/settings.html', form=form)
