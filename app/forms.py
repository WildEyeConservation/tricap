# D Joubert Innoventix Consulting 14 November 2016
# Forms for the GUI

from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, SubmitField, FieldList

class SettingsForm(FlaskForm):
    """The form for the settings page. Contains the three buttons (test, save and revert) and
    the FieldLists that must be expanded with the settings read from the config file."""

    misc_strings = FieldList(StringField(), min_entries=0)
    misc_selects = FieldList(SelectField(), min_entries=0)
    cam_strings = FieldList(StringField(), min_entries=0)
    cam_selects = FieldList(SelectField(), min_entries=0)
    alti_strings = FieldList(StringField(), min_entries=0)
    alti_selects = FieldList(SelectField(), min_entries=0)
    web_strings = FieldList(StringField(), min_entries=0)
    web_selects = FieldList(SelectField(), min_entries=0)
    sms_strings = FieldList(StringField(), min_entries=0)
    sms_selects = FieldList(SelectField(), min_entries=0)

    # set = SubmitField(label='Set')
    save = SubmitField(label='Save')
    revert = SubmitField(label='Revert')
