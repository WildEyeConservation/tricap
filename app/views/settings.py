import os

import pdb

from flask import Blueprint, render_template, send_file, request, jsonify, redirect, url_for

from app import forms, tricap_manager
from sensors.utilities import read_init_config, save_config

from config import SERVER_LOG_DIR, DEFAULT_CONFIG_FP

settings_bp = Blueprint('settings', __name__)

def _get_form_with_current_settings():
    form = forms.SettingsForm()

    current_shutterspeed_str = tricap_manager.get_shutter_speed_as_string()
    print(current_shutterspeed_str)
    choice_strings = [choice[1] for choice in form.shutter_speed.choices]
    if current_shutterspeed_str in choice_strings:
        form.shutter_speed.data = str(choice_strings.index(current_shutterspeed_str))

    form.image_capture_interval.data = tricap_manager.get_image_capture_interval()
    form.server_log_dir.data = SERVER_LOG_DIR

    return form

def _change_settings(form):
    ss_dict = dict(form.shutter_speed.choices)
    tricap_manager.set_shutterspeed(ss_dict[form.shutter_speed.data])
    tricap_manager.set_image_capture_interval(float(form.image_capture_interval.data))

def _save_settings(form):
    _change_settings(form)

    # TODO Should do an error check here, if there are errors, don't save
    init_config = read_init_config()

    ss_dict = dict(form.shutter_speed.choices)
    init_config['shutterspeed'] = ss_dict[form.shutter_speed.data]
    init_config['image_capture_interval'] = form.image_capture_interval.data

    save_config(init_config)

def _revert_to_default_settings(save_to_fp=None):
    default_config = read_init_config(config_fp = DEFAULT_CONFIG_FP)
    save_config(default_config, save_to_fp=save_to_fp)

    # TODO Edit the stuff further here

@settings_bp.route('/settings', methods=['GET', 'POST'])
def settings():

    if request.method == 'GET':
        form = _get_form_with_current_settings()
        print(form.image_capture_interval.data)
    else:
        form = forms.SettingsForm(request.form)

    if form.validate_on_submit():
        if form.test.data is True:
            _change_settings(form)
        elif form.save.data is True:
            _save_settings(form)
        elif form.revert.data is True:
            _revert_to_default_settings()

        return redirect(url_for('home.index'))

    return render_template('/settings/settings.html', form=form)
