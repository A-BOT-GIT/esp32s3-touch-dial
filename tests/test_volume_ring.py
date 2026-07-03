from math import isclose


def fill_end(volume, arc_start=135, arc_end=405):
    return round(arc_start + (arc_end - arc_start) * volume / 100)


def segment_to_redraw(old_volume, new_volume, arc_start=135, arc_end=405):
    old_end = fill_end(old_volume, arc_start, arc_end)
    new_end = fill_end(new_volume, arc_start, arc_end)
    if new_end > old_end:
        return (old_end + 1, new_end, 1, "active")
    if new_end < old_end:
        return (old_end, new_end + 1, -1, "erase")
    return None


def point_to_volume(x, y, cx=120, cy=120, inner_radius=70, outer_radius=125):
    """Python reference for firmware volume ring math.

    270-degree arc: left-bottom = 0, top = 50, right-bottom = 100.
    Coordinates use screen convention: x right, y down.
    """
    import math

    dx = x - cx
    dy = y - cy
    r = math.hypot(dx, dy)
    if r < inner_radius or r > outer_radius:
        return None

    deg = math.degrees(math.atan2(dy, dx))
    if deg < 0:
        deg += 360

    if 135 <= deg <= 270:
        progress = (deg - 135) / 270
    elif 270 < deg <= 360:
        progress = (deg - 135) / 270
    elif 0 <= deg <= 45:
        progress = (deg + 360 - 135) / 270
    else:
        return None

    return max(0, min(100, round(progress * 100)))


def apply_encoder_step(volume, direction, step=2):
    if direction == "RIGHT":
        return min(100, volume + step)
    if direction == "LEFT":
        return max(0, volume - step)
    return volume


def encoder_debug_line(source, direction, active):
    state = "RUN" if active else "IDLE"
    return f"{source} {direction} {state}".strip()


def test_left_bottom_is_zero():
    assert point_to_volume(49, 191) == 0


def test_top_is_around_50():
    assert 48 <= point_to_volume(120, 20) <= 52


def test_right_bottom_is_100():
    assert point_to_volume(191, 191) == 100


def test_center_is_ignored():
    assert point_to_volume(120, 120) is None


def test_gap_at_bottom_is_ignored():
    assert point_to_volume(120, 220) is None


def test_outside_screen_is_ignored():
    assert point_to_volume(300, 300) is None


def test_right_side_is_about_83_percent():
    assert 82 <= point_to_volume(220, 120) <= 84


def test_decrease_only_redraws_old_tail_segment():
    start, end, step, mode = segment_to_redraw(80, 20)
    assert mode == "erase"
    assert step == -1
    assert start == fill_end(80)
    assert end == fill_end(20) + 1


def test_increase_only_redraws_new_head_segment():
    start, end, step, mode = segment_to_redraw(20, 80)
    assert mode == "active"
    assert step == 1
    assert start == fill_end(20) + 1
    assert end == fill_end(80)


def test_encoder_right_increases_volume_with_clamp():
    assert apply_encoder_step(50, "RIGHT") == 52
    assert apply_encoder_step(99, "RIGHT") == 100


def test_encoder_left_decreases_volume_with_clamp():
    assert apply_encoder_step(50, "LEFT") == 48
    assert apply_encoder_step(1, "LEFT") == 0


def test_encoder_debug_line_formats_state_and_direction():
    assert encoder_debug_line("ENC", "RIGHT", True) == "ENC RIGHT RUN"
    assert encoder_debug_line("SIM", "LEFT", False) == "SIM LEFT IDLE"
