import RPi.GPIO as GPIO
import time

GPIO.setmode(GPIO.BCM)

SWITCH_PIN = 22
RED_PIN = 17
GREEN_PIN = 27

time.sleep(200e-3)

GPIO.setup(GREEN_PIN, GPIO.OUT)
GPIO.setup(RED_PIN, GPIO.OUT)

GPIO.cleanup()

GPIO.setmode(GPIO.BCM)

GPIO.setup(GREEN_PIN, GPIO.OUT)
GPIO.setup(RED_PIN, GPIO.OUT)

GPIO.output(RED_PIN, GPIO.LOW)
GPIO.output(GREEN_PIN, GPIO.LOW)

time.sleep(100e-3)

red_pwm = GPIO.PWM(RED_PIN, 0.5)
green_pwm = GPIO.PWM(GREEN_PIN, 0.5)

red_pwm.stop()
green_pwm.stop()

time.sleep(100e-3)

GPIO.cleanup()

