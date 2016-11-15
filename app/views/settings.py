import os

from flask import Blueprint, render_template, send_file, request, jsonify, redirect, url_for

from app import forms, tricap_manager

from config import SERVER_LOG_DIR

settings_bp = Blueprint('settings', __name__)

def _get_form_with_current_settings():
    form = forms.SettingsForm()

    current_shutterspeed_str = tricap_manager.get_shutter_speed_as_string()
    choice_strings = [choice[1] for choice in form.shutter_speed.choices]
    if current_shutterspeed_str in choice_strings:
        form.shutter_speed.data = str(choice_strings.index(current_shutterspeed_str))

    form.image_capture_interval.data = tricap_manager.get_image_capture_interval()
    form.server_log_dir.data = SERVER_LOG_DIR

    return form

def _change_settings(form):
    pass

@settings_bp.route('/settings', methods=['GET', 'POST'])
def settings():

    if request.method == 'GET':
        form = _get_form_with_current_settings()
    else:
        form = forms.SettingsForm(request.form)

    if form.validate_on_submit():
        _change_settings(form)
        return redirect(url_for('home.index'))

    return render_template('/settings/settings.html', form=form)
