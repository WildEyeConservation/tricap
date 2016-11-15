# D Joubert Innoventix Consulting 14 November 2016
# Forms for the GUI

from flask_wtf import Form
from wtforms import StringField, IntegerField, SelectField, SubmitField
from wtforms.validators import Required

from config import SERVER_LOG_DIR

class SettingsForm(Form):
    """The form for the settings page"""
    image_capture_interval = StringField(label='Image capture interval', validators=[Required()])
    shutter_speed = SelectField(label='Shutter speed', choices=[('0', '1/2500'), ('1', '1/640'),
                                                                ('2', '1/4')], default='0')
    server_log_dir = StringField(label='Log directory', default=SERVER_LOG_DIR)
    test = SubmitField(label='Test')
    save = SubmitField(label='Save')
