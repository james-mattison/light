# light

---

_Library for interacting with Philip Hue Lights_

## Description:

This project contains two primary files:
- `light.py`, which contains a library for interacting with the lights. Allows command-line arguments.
- `glight.py`, which contains a GTK interface for `light.py`


## Requirements:

1. **Hue Bridge**: In order to interact with the lights, you need to have purchased a Hue Bridge, and have it
already set up.
2. **Hue Developer Account**: This is free, and is the source of the username that is used to interact with the lights. [Sign up here](https://developers.meethue.com/).
3. **Environmental Variables**:
- ```LIGHT_UNIT``` -The IP address on the local network of the Bridge
- ```LIGHT_USER``` -The username retreived from the Hue Developer Account.
