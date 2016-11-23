import os

import pdb

from flask import Blueprint, render_template, send_file, request, jsonify, redirect, url_for
from flask import current_app
from wtforms import StringField, IntegerField, SelectField

from app import forms, tricap_manager, altimeter
from sensors.configure import TricapConfig

from config import SERVER_LOG_DIR, DEFAULT_CONFIG_FP, CONFIG_FP, RET_OK

settings_bp = Blueprint('settings', __name__)

""" There should be three sources of settings, the cameras, the altimeter and general settings """

# def _get_blank_setting_form_class(config_fp = CONFIG_FP):
#     class FormClass(forms.SettingsForm):
#         pass
#
#     config = TricapConfig(current_app.logger, config_fp_to_read=config_fp)
#     config_dict = config.get_dict()
#
#     for key in config_dict.keys():
#         choices = tricap_manager.get_choices_for_config(key)
#         if choices is not None and len(choices) != 0:
#             setattr(FormClass, key, SelectField(label=key, choices=choices))
#         else:
#             setattr(FormClass, key, StringField(label=key))
#
#     return FormClass

def _get_setting_form(config_fp=CONFIG_FP, config_dict=None):
    form = forms.SettingsForm()

    if config_dict is None:
        config = TricapConfig(current_app.logger, config_fp_to_read=config_fp)
        config_dict = config.get_dict()

    for key in config_dict.keys():
        choices = tricap_manager.get_choices_for_config(key)
        if choices is not None and len(choices) != 0:
            form.select_settings.append_entry()
            form.select_settings[-1].label = key
            choices_tuples = []
            for index, choice in enumerate(choices):
                choices_tuples.append((str(index), choice))
            form.select_settings[-1].choices = choices_tuples
        else:
            form.string_settings.append_entry()
            form.string_settings[-1].label = key

    return form

def _get_setting_labels(form):
    string_labels = []
    select_labels = []
    for string_setting in form.string_settings:
        string_labels.append(string_setting.label)
    for select_setting in form.select_settings:
        select_labels.append(select_setting.label)

    return string_labels, select_labels

def _get_form_with_current_settings(config_fp = CONFIG_FP):
    config = TricapConfig(current_app.logger, config_fp_to_read=config_fp)
    config_dict = config.get_dict()

    form = _get_setting_form(config_dict=config_dict)
    string_labels, select_labels = _get_setting_labels(form)

    # populate the form data members
    for key in config_dict.keys():
        config_val = tricap_manager.get_setting(key)
        if config_val is not None:
            if key in string_labels:
                form.string_settings[string_labels.index(key)].data = config_val
            elif key in select_labels:
                choices_tuples = form.select_settings[select_labels.index(key)].choices
                choices = [ct[1] for ct in choices_tuples]
                form.select_settings[select_labels.index(key)].data = choices.index(config_val)
        else: # it's not a camera settings
            config_val = altimeter.get_setting(key)
            if config_val is not None:
                if key in string_labels:
                    form.string_settings[string_labels.index(key)].data = config_val
            else: # it's not an altimeter setting either
                pass # here should go specific setting value handling

    # current_shutterspeed_str = tricap_manager.get_shutter_speed_as_string()
    # print(current_shutterspeed_str)
    # choice_strings = [choice[1] for choice in form.shutterspeed.choices]
    # if current_shutterspeed_str in choice_strings:
    #     form.shutterspeed.data = str(choice_strings.index(current_shutterspeed_str))
    #
    # form.image_capture_interval.data = tricap_manager.get_image_capture_interval()
    # form.server_log_dir.data = SERVER_LOG_DIR

    return form

def _change_settings(form):
    string_labels, select_labels = _get_setting_labels(form)

    for index, sel_l in enumerate(select_labels):
        choice_index = int(form.select_settings[index].data)
        choice_val_str = form.select_settings[index].choices[choice_index][1]
        # check the three config sources/sinks
        if tricap_manager.set_setting(sel_l, choice_val_str) == RET_OK:
            continue
        if altimeter.set_setting(sel_l, choice_val_str) == RET_OK:
            continue
        # TODO Do something with general settings

    for index, str_l in enumerate(string_labels):
        val_str = form.string_settings[index].data
        # check the three config sources/sinks
        if tricap_manager.set_setting(str_l, val_str) == RET_OK:
            continue
        if altimeter.set_setting(str_l, val_str) == RET_OK:
            continue
        # TODO Do something with general settings

    # ss_dict = dict(form.shutter_speed.choices)
    # tricap_manager.set_shutterspeed(ss_dict[form.shutter_speed.data])
    # tricap_manager.set_image_capture_interval(float(form.image_capture_interval.data))

def _save_settings(form):
    _change_settings(form)

    config = TricapConfig(current_app.logger)
    config_dict = config.get_dict()

    string_labels, select_labels = _get_setting_labels(form)

    for index, sel_l in enumerate(select_labels):
        choice_index = int(form.select_settings[index].data)
        choice_val_str = form.select_settings[index].choices[choice_index][1]
        config_dict[sel_l] = choice_val_str

    for index, str_l in enumerate(string_labels):
        val_str = form.string_settings[index].data
        config_dict[str_l] = val_str

    # ss_dict = dict(form.shutter_speed.choices)
    # config_dict['shutterspeed'] = ss_dict[form.shutter_speed.data]
    # config_dict['image_capture_interval'] = form.image_capture_interval.data

    config.save_config_dict_to_file(config_dict)

def _revert_to_default_settings(save_to_fp=CONFIG_FP, logger=None):
    # arguments are only supposed to be used during unittesting
    if logger is None:
        logger = current_app.logger

    default_config = TricapConfig(logger, config_fp_to_read=DEFAULT_CONFIG_FP)
    config = TricapConfig(logger, config_fp_to_read=save_to_fp)
    config.save_config_dict_to_file(default_config.get_dict())

@settings_bp.route('/settings', methods=['GET', 'POST'])
def settings():

    if request.method == 'GET':
        # When the user initially opens the page, we need the current settings from the sensors
        form = _get_form_with_current_settings()
    else:
        # formClass = _get_blank_setting_form_class()
        # form = formClass(request.form)
        form = forms.SettingsForm(request.form)

    if form.validate_on_submit():
        tricap_manager.stop_capturing()
        altimeter.stop_measuring()

        if form.test.data is True:
            _change_settings(form)
        elif form.save.data is True:
            _save_settings(form)
        elif form.revert.data is True:
            _revert_to_default_settings()

        return redirect(url_for('home.index'))

    return render_template('/settings/settings.html', form=form)
