from ghostwake.tactical import PATROL_BASES, calculate_intercept


def test_patrol_bases_defined():
    assert "ICGS Mandapam" in PATROL_BASES
    assert "ICGS Thoothukudi" in PATROL_BASES
    assert PATROL_BASES["ICGS Mandapam"]["lat"] == 9.278
    assert PATROL_BASES["ICGS Mandapam"]["lon"] == 79.125


def test_stationary_target_intercept():
    # Target stationary near Palk Bay (9.4, 79.3)
    res = calculate_intercept(
        target_lat=9.4,
        target_lon=79.3,
        target_speed_knots=0.0,
        target_heading_deg=0.0,
        patrol_base_name="ICGS Mandapam",
        patrol_speed_knots=30.0,
    )
    assert res.possible is True
    assert res.time_minutes is not None
    assert 10.0 < res.time_minutes < 60.0
    assert res.intercept_lat == 9.4
    assert res.intercept_lon == 79.3
    assert res.imbl_status in ("indian_waters", "near_imbl", "crossed_imbl")


def test_moving_target_intercept():
    # Target moving east at 10 knots from Gulf of Mannar
    res = calculate_intercept(
        target_lat=9.0,
        target_lon=79.2,
        target_speed_knots=10.0,
        target_heading_deg=90.0,
        patrol_base_name="ICGS Mandapam",
        patrol_speed_knots=32.0,
    )
    assert res.possible is True
    assert res.time_minutes is not None
    assert res.time_minutes > 0
    assert res.intercept_lon > 79.2  # Moved east
    assert res.distance_nm > 0
    assert "Mandapam" in res.tactical_summary


def test_impossible_intercept_target_too_fast():
    # Target moving east away from patrol craft at 50 knots while patrol is only 20 knots
    res = calculate_intercept(
        target_lat=9.0,
        target_lon=79.9,
        target_speed_knots=50.0,
        target_heading_deg=90.0,
        patrol_base_name="ICGS Mandapam",
        patrol_speed_knots=20.0,
    )
    assert res.possible is False
    assert "impossible" in res.tactical_summary.lower()
