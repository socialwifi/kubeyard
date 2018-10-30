from termcolor import cprint
from pyfiglet import figlet_format


TEXT = 'Social WiFi\nCLI'
FONT_COLOR = 'cyan'
FONT = 'standard'


def print_ascii_art():
    ascii_art = figlet_format(TEXT, font=FONT, justify='center')
    cprint(ascii_art, FONT_COLOR, attrs=['bold'])
