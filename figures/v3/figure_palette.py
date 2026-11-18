"""Shared manuscript colours; retain the established yellow; Fig5 specifies translucent dark-grey markers."""

BLUE = '#7E99F4'
RED = '#CC7C71'
GREEN = '#7AB656'
GRAY = '#A5AEB7'
YELLOW = '#C9A45C'
GOLD = '#C6A253'

PALETTE = dict(blue=BLUE, red=RED, green=GREEN, gray=GRAY, yellow=YELLOW)
YEAR_COLORS = {1998: BLUE, 2007: RED, 2016: GREEN, 2025: YELLOW}


def tint(hex_color, white_fraction):
    """Mix a palette colour with white, retaining its hue family."""
    assert 0 <= white_fraction <= 1
    rgb = [int(hex_color[i:i + 2], 16) for i in (1, 3, 5)]
    mixed = [round(v * (1 - white_fraction) + 255 * white_fraction) for v in rgb]
    return '#' + ''.join(f'{v:02X}' for v in mixed)


# A balanced blue-green and warm-apricot family distinguishes countries from years.
COUNTRY_COLORS = {'US': '#397F8E', 'DE': '#8DBCC8',
                  'GB': '#D69C7A', 'JP': '#E5CBA5', 'CN': '#89A99E'}
OTHER_COLOR = tint(GRAY, .65)
assert set(COUNTRY_COLORS.values()).isdisjoint(YEAR_COLORS.values())
