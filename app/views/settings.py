from flask import Blueprint, render_template, request, redirect, url_for
from flask import current_app

from app import forms, tricap_manager, altimeter, session_logger
from config import DEFAULT_CONFIG_FP, CONFIG_FP, RET_OK, RET_ERROR
from sensors.configure import TricapConfig

settings_bp = Blueprint('settings', __name__)

""" There should be three sources of settings, the cameras, the altimeter and general settings """


class MiscSettingHandler:
    """ Handles all the settings which are not applicable to the sensors """

    def __init__(self):
        self._setting_strings = ['session_description', 'image_capture_interval']

    def set_setting(self, setting_str, val_str):
        if setting_str in self._setting_strings:
            if setting_str == 'session_description':
                return session_logger.set_description(val_str)
            elif setting_str == 'image_capture_interval':
                return tricap_manager.set_image_capture_interval(val_str)
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

def _get_labels_and_choices_from_config(config_fp=CONFIG_FP, config_dict=None):
    select_tuples = []
    string_labels = []

    if config_dict is None:
        config = TricapConfig(current_app.logger, config_fp_to_read=config_fp)
        config_dict = config.get_dict()

    for key in config_dict.keys():
        choices = tricap_manager.get_choices_for_setting(key)
        if choices is not None and len(choices) != 0:
            choices_tuples = []
            for index, choice in enumerate(choices):
                choices_tuples.append((str(index), choice))

            select_tuples.append((key, choices_tuples))
        else:
            string_labels.append(key)

    return string_labels, select_tuples


def _get_setting_form(config_fp=CONFIG_FP, config_dict=None):
    form = forms.SettingsForm()

    string_labels, select_tuples = _get_labels_and_choices_from_config(config_fp=config_fp,
                                                                       config_dict=config_dict)
    for sel_tup in select_tuples:
        form.select_settings.append_entry()
        form.select_settings[-1].label = sel_tup[0]
        form.select_settings[-1].choices = sel_tup[1]

    for str_lbl in string_labels:
        form.string_settings.append_entry()
        form.string_settings[-1].label = str_lbl

    return form


def _populated_pushed_form(pushed_form, config_fp=CONFIG_FP, config_dict=None):
    """ for some reason, the pushed form loses the labels of the added fields, so have to add em"""
    string_labels, select_tuples = _get_labels_and_choices_from_config(config_fp=config_fp,
                                                                       config_dict=config_dict)
    for index in range(len(string_labels)):
        pushed_form.string_settings[index].label = string_labels[index]

    for index in range(len(select_tuples)):
        pushed_form.select_settings[index].label = select_tuples[index][0]
        pushed_form.select_settings[index].choices = select_tuples[index][1]

    return pushed_form


def _get_setting_labels(form):
    string_labels = []
    select_labels = []
    for string_setting in form.string_settings:
        string_labels.append(string_setting.label)
    for select_setting in form.select_settings:
        select_labels.append(select_setting.label)

    return string_labels, select_labels


def _get_form_with_current_settings(config_fp=CONFIG_FP):
    config = TricapConfig(current_app.logger, config_fp_to_read=config_fp)
    config_dict = config.get_dict()

    form = _get_setting_form(config_dict=config_dict)
    string_labels, select_labels = _get_setting_labels(form)

    misc_setting_handler = MiscSettingHandler()

    # populate the form data members
    for key in config_dict.keys():
        config_val = tricap_manager.get_setting(key)
        if config_val is not None:
            if key in string_labels:
                form.string_settings[string_labels.index(key)].data = config_val
            elif key in select_labels:
                choices_tuples = form.select_settings[select_labels.index(key)].choices
                choices = [ct[1] for ct in choices_tuples]
                form.select_settings[select_labels.index(key)].data = str(choices.index(config_val))
        else:  # it's not a camera settings
            config_val = altimeter.get_setting(key)
            if config_val is not None:
                if key in string_labels:
                    form.string_settings[string_labels.index(key)].data = config_val
            else:  # it's not an altimeter setting either
                config_val = misc_setting_handler.get_setting(key)
                if config_val is not None:
                    if key in string_labels:
                        form.string_settings[string_labels.index(key)].data = config_val

    return form


def _change_settings(form):
    string_labels, select_labels = _get_setting_labels(form)

    misc_setting_handler = MiscSettingHandler()

    for index, sel_l in enumerate(select_labels):
        choice_index = int(form.select_settings[index].data)
        choice_val_str = form.select_settings[index].choices[choice_index][1]
        # check the three config sources/sinks
        if tricap_manager.set_setting(sel_l, choice_val_str) == RET_OK:
            continue
        if altimeter.set_setting(sel_l, choice_val_str) == RET_OK:
            continue
        if misc_setting_handler.set_setting(sel_l, choice_val_str) == RET_OK:
            continue

    for index, str_l in enumerate(string_labels):
        val_str = form.string_settings[index].data
        # check the three config sources/sinks
        if tricap_manager.set_setting(str_l, val_str) == RET_OK:
            continue
        if altimeter.set_setting(str_l, val_str) == RET_OK:
            continue
        if misc_setting_handler.set_setting(str_l, val_str) == RET_OK:
            continue


def _save_settings(form, config_fp=CONFIG_FP, logger=None):
    # If no logger is specified, use the apps logger (having it as default
    #  freaks out the app initialisation)
    if logger is None:
        logger = current_app.logger

    _change_settings(form)

    # get the current settings in a dict
    config = TricapConfig(logger, config_fp_to_read=config_fp)
    config_dict = config.get_dict()

    # modify the settings dict based on settings in the form (i.e. the user selected options)
    string_labels, select_labels = _get_setting_labels(form)

    for index, sel_l in enumerate(select_labels):
        choice_index = int(form.select_settings[index].data)
        choice_val_str = form.select_settings[index].choices[choice_index][1]
        config_dict[sel_l] = choice_val_str

    for index, str_l in enumerate(string_labels):
        val_str = form.string_settings[index].data
        config_dict[str_l] = val_str

    config.save_config_dict_to_file(config_dict)


def _revert_to_default_settings(save_to_fp=CONFIG_FP, logger=None):
    # arguments are only supposed to be used during unittesting
    if logger is None:
        logger = current_app.logger

    default_config = TricapConfig(logger, config_fp_to_read=DEFAULT_CONFIG_FP)
    config = TricapConfig(logger, config_fp_to_read=save_to_fp)
    config.clear_config()
    config.save_config_dict_to_file(default_config.get_dict())


@settings_bp.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'GET':
        # When the user initially opens the page, we need the current settings from the sensors
        form = _get_form_with_current_settings()
    else:
        # when the users posts (i.e. clicks one of the submit buttons) we need to base the form
        #  on the user selected settings
        form = _populated_pushed_form(forms.SettingsForm(request.form))

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
