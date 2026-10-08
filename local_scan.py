#!/usr/bin/env python3

"""Local scan pipeline for the v8 desktop UI.

This module contains no Google Sheets calls and uses the dedicated v8
Google-free Finder engine.
"""

import community_deposits
import finder_engine as engine
import system_filter_search


DISTANCE_HEADER = "Distance (LY)"
SYSTEM_HEADERS = ["System", "Population", "Power State", "Powerplay Progress"]


class LocalScanError(RuntimeError):
    pass


def normalize_config(config):
    config = dict(config or {})

    systems = engine.deduplicate([
        str(value).strip()
        for value in config.get("systems", [])
        if str(value).strip()
    ])

    reference_system = str(
        config.get("reference_system", "") or ""
    ).strip()

    max_distance_raw = str(
        config.get("max_distance_ly", "50") or ""
    ).strip()
    if not max_distance_raw:
        max_distance_raw = "50"

    max_distance_ly = 50.0
    if reference_system:
        try:
            max_distance_ly = float(max_distance_raw.replace(",", "."))
        except ValueError as exc:
            raise LocalScanError(
                "Max Distance (LY) must be a number."
            ) from exc

        if max_distance_ly <= 0:
            raise LocalScanError(
                "Max Distance (LY) must be greater than 0."
            )

    normalized = {
        "systems": systems,
        "hotspots_enabled": bool(config.get("hotspots_enabled", False)),
        "planets_enabled": bool(config.get("planets_enabled", False)),
        "ring_types": {
            "icy": False,
            "metallic": False,
            "metal rich": False,
            "rocky": False,
            **dict(config.get("ring_types", {})),
        },
        "materials": {
            "platinum": False,
            "bromellite": False,
            "monazite": False,
            **dict(config.get("materials", {})),
        },
        "only_pristine": bool(config.get("only_pristine", False)),
        "only_landables": bool(config.get("only_landables", False)),
        "planet_types": {
            "icy": False,
            "metal rich": False,
            "high metal content": False,
            "rocky": False,
            "rocky ice": False,
            **dict(config.get("planet_types", {})),
        },
        "faction_name": str(config.get("faction_name", "") or "").strip(),
        "power_name": str(config.get("power_name", "") or "").strip(),
        "power_states": {
            "Unoccupied": False,
            "Exploited": False,
            "Fortified": False,
            "Stronghold": False,
            **dict(config.get("power_states", {})),
        },
        "reference_system": reference_system,
        "max_distance_ly": max_distance_ly,
        "community_deposits_enabled": bool(
            config.get("community_deposits_enabled", False)
        ),
    }

    return normalized


def _nothing_enabled(config):
    return (
        not config["hotspots_enabled"]
        and not config["planets_enabled"]
        and not config["community_deposits_enabled"]
    )


def _selected_power_states(config):
    if not config["power_name"]:
        return []
    return [
        state
        for state, enabled in config["power_states"].items()
        if enabled
    ]


def _has_system_filters(config):
    return bool(
        config["faction_name"]
        or config["power_name"]
        or config["reference_system"]
    )


def _format_result_distance(value):
    if value in (None, ""):
        return ""
    try:
        return f"{float(value):.2f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return str(value)


def _add_distance_column(headers, rows, distances):
    """Insert Distance (LY) after System and populate visible system rows."""

    headers = list(headers or [])
    if DISTANCE_HEADER not in headers:
        try:
            system_index = headers.index("System")
        except ValueError:
            headers.append(DISTANCE_HEADER)
        else:
            headers.insert(system_index + 1, DISTANCE_HEADER)

    output_rows = []
    last_system = ""
    for source in rows or []:
        row = dict(source)
        system_name = str(row.get("System", "") or "").strip()
        if system_name:
            last_system = system_name
            row[DISTANCE_HEADER] = _format_result_distance(
                distances.get(engine.norm(system_name), "")
            )
        else:
            # Compact Hotspots/Planets rows intentionally blank System on
            # repeated lines; keep Distance blank there as well.
            row[DISTANCE_HEADER] = ""
        output_rows.append(row)

    return headers, output_rows


def _format_population(value):
    if value in (None, ""):
        return ""
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


def _format_powerplay_progress(value):
    if value in (None, ""):
        return ""
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return str(value)


def _build_system_results(systems, distances, metadata, show_distance):
    headers = list(SYSTEM_HEADERS)
    if show_distance:
        headers.remove(DISTANCE_HEADER) if DISTANCE_HEADER in headers else None
        headers.insert(0, DISTANCE_HEADER)

    rows = []
    metadata = metadata or {}
    for system in systems:
        key = engine.norm(system)
        info = metadata.get(key) or {}
        row = {
            "System": system,
            "Population": _format_population(info.get("Population", "")),
            "Power State": str(info.get("Power State", "") or ""),
            "Powerplay Progress": _format_powerplay_progress(
                info.get("Powerplay Progress", "")
            ),
        }
        if show_distance:
            row[DISTANCE_HEADER] = _format_result_distance(
                distances.get(key, "")
            )
        rows.append(row)
    return headers, rows


def _intersect_systems(base_systems, allowed_systems, *, prefer_allowed_order=False):
    base_systems = engine.deduplicate(base_systems or [])
    allowed_systems = engine.deduplicate(allowed_systems or [])
    base_keys = {engine.norm(system) for system in base_systems}
    allowed_keys = {engine.norm(system) for system in allowed_systems}

    source = allowed_systems if prefer_allowed_order else base_systems
    other = base_keys if prefer_allowed_order else allowed_keys
    return [system for system in source if engine.norm(system) in other]


def _resolve_systems(config, cancel_event=None):
    """Resolve the effective system set without mutating the manual input list.

    Manual systems are an input candidate set. Faction / Power / State /
    Reference / Distance narrow that set when present. If the manual list is
    empty, those filters generate the candidate set internally.
    """

    manual_systems = list(config["systems"])
    faction_name = config["faction_name"]
    power_name = config["power_name"]
    reference_system = config["reference_system"]
    max_distance_ly = config["max_distance_ly"]
    selected_power_states = _selected_power_states(config)

    if not _has_system_filters(config):
        metadata = system_filter_search.enrich_system_metadata(
            manual_systems,
            cancel_event=cancel_event,
        )
        return manual_systems, {}, metadata

    # A manual list + Reference only is a small candidate set, so use direct
    # coordinate filtering rather than asking Spansh for every system in the
    # surrounding sphere and intersecting afterwards.
    if manual_systems and reference_system and not faction_name and not power_name:
        return system_filter_search.filter_systems_within_distance(
            reference_system,
            manual_systems,
            max_distance_ly=max_distance_ly,
            cancel_event=cancel_event,
        )

    resolved, distances, metadata = system_filter_search.search_systems_by_filters(
        faction_name,
        power_name,
        selected_power_states,
        reference_system=reference_system,
        max_distance_ly=max_distance_ly,
        include_distances=True,
        cancel_event=cancel_event,
    )

    if not manual_systems:
        return resolved, distances, metadata

    effective = _intersect_systems(
        manual_systems,
        resolved,
        prefer_allowed_order=bool(reference_system),
    )
    effective_keys = {engine.norm(system) for system in effective}
    distances = {
        key: value
        for key, value in distances.items()
        if key in effective_keys
    }
    metadata = {
        key: value
        for key, value in metadata.items()
        if key in effective_keys
    }
    return effective, distances, metadata


def _community_systems(rows):
    return engine.deduplicate([
        str(row.get("System", "") or "").strip()
        for row in rows or []
        if str(row.get("System", "") or "").strip()
    ])


def _filter_community_rows(rows, systems):
    allowed = {engine.norm(system) for system in systems or []}
    if not allowed:
        return []
    return [
        dict(row)
        for row in rows or []
        if engine.norm(row.get("System", "")) in allowed
    ]


def _load_community_results(
    config,
    *,
    shared_systems=None,
    shared_distances=None,
    cancel_event=None,
):
    """Fetch the Community database once and filter it locally.

    When Hotspots/Planets already resolved systems, reuse that set. In a
    Community-only scan, start from systems which actually have database rows
    and apply manual/System Filters to that much smaller candidate set.
    """

    headers, all_rows = community_deposits.fetch_all_deposits(
        cancel_event=cancel_event,
    )
    engine.check_cancel(cancel_event)

    if shared_systems is not None:
        systems = list(shared_systems)
        distances = dict(shared_distances or {})
        rows = _filter_community_rows(all_rows, systems)
        return headers, rows, systems, distances

    database_systems = _community_systems(all_rows)
    manual_systems = list(config["systems"])

    if manual_systems:
        database_systems = _intersect_systems(
            manual_systems,
            database_systems,
            prefer_allowed_order=False,
        )

    candidate_config = dict(config)
    candidate_config["systems"] = database_systems

    if _has_system_filters(candidate_config):
        systems, distances, _metadata = _resolve_systems(
            candidate_config,
            cancel_event=cancel_event,
        )
    else:
        systems, distances = database_systems, {}

    rows = _filter_community_rows(all_rows, systems)
    return headers, rows, systems, distances


def _empty_result(
    status,
    config,
    *,
    systems=None,
    system_distances=None,
    system_metadata=None,
):
    systems = list(systems or [])
    system_distances = dict(system_distances or {})
    system_metadata = dict(system_metadata or {})
    system_headers, system_rows = _build_system_results(
        systems,
        system_distances,
        system_metadata,
        bool(config["reference_system"]),
    )
    return {
        "status": status,
        "systems": systems,
        "system_headers": system_headers,
        "system_rows": system_rows,
        "hotspot_headers": list(engine.HOTSPOT_HEADERS),
        "hotspot_rows": [],
        "planet_headers": list(engine.PLANET_HEADERS),
        "planet_rows": [],
        "community_headers": list(community_deposits.COMMUNITY_HEADERS),
        "community_rows": [],
        "unresolved": [],
        "summary": {
            "status": status,
            "systems_found": len(systems),
            "faction_name": config["faction_name"],
            "power_name": config["power_name"],
            "power_state_filters": _selected_power_states(config),
            "reference_system": config["reference_system"],
            "max_distance_ly": (
                config["max_distance_ly"]
                if config["reference_system"]
                else None
            ),
            "hotspots_enabled": config["hotspots_enabled"],
            "planets_enabled": config["planets_enabled"],
            "community_deposits_enabled": config["community_deposits_enabled"],
        },
    }


def run_local_scan(config, cancel_event=None):
    """Run the Finder logic and return data directly to the GUI."""

    engine.check_cancel(cancel_event)
    config = normalize_config(config)

    reference_system = config["reference_system"]
    max_distance_ly = config["max_distance_ly"]
    outputs_enabled = not _nothing_enabled(config)
    hp_enabled = config["hotspots_enabled"] or config["planets_enabled"]

    # No result type enabled means System List mode. The manual Systems box is
    # never overwritten; resolved systems are returned for the dedicated tab.
    if not outputs_enabled:
        if not config["systems"] and not _has_system_filters(config):
            raise LocalScanError(
                "Add at least one manual system or set a System Filter."
            )

        systems, system_distances, system_metadata = _resolve_systems(
            config,
            cancel_event=cancel_event,
        )
        engine.check_cancel(cancel_event)

        system_headers, system_rows = _build_system_results(
            systems,
            system_distances,
            system_metadata,
            bool(reference_system),
        )
        return {
            "status": "SYSTEM_LIST_READY",
            "systems": systems,
            "system_headers": system_headers,
            "system_rows": system_rows,
            "hotspot_headers": list(engine.HOTSPOT_HEADERS),
            "hotspot_rows": [],
            "planet_headers": list(engine.PLANET_HEADERS),
            "planet_rows": [],
            "community_headers": list(community_deposits.COMMUNITY_HEADERS),
            "community_rows": [],
            "unresolved": [],
            "summary": {
                "status": "SYSTEM_LIST_READY",
                "systems_found": len(systems),
                "faction_name": config["faction_name"],
                "power_name": config["power_name"],
                "power_state_filters": _selected_power_states(config),
                "reference_system": reference_system,
                "max_distance_ly": max_distance_ly if reference_system else None,
                "hotspots_enabled": False,
                "planets_enabled": False,
                "community_deposits_enabled": False,
            },
        }

    systems = []
    system_distances = {}
    system_metadata = {}

    # Hotspots/Planets require a finite system candidate set. Community-only is
    # allowed with no Systems/System Filters and simply returns the whole DB.
    if hp_enabled:
        if not config["systems"] and not _has_system_filters(config):
            raise LocalScanError(
                "Hotspots/Planets require manual systems or a System Filter."
            )

        systems, system_distances, system_metadata = _resolve_systems(
            config,
            cancel_event=cancel_event,
        )
        engine.check_cancel(cancel_event)

        if not systems:
            return _empty_result(
                "NO_SYSTEMS_MATCHING_FILTERS",
                config,
            )

    print(f"Hotspots: {config['hotspots_enabled']}")
    print(f"Planets: {config['planets_enabled']}")
    print(f"Community Deposits: {config['community_deposits_enabled']}")
    if hp_enabled:
        print(f"Resolved systems: {len(systems)}")
    if reference_system:
        print(
            f"Reference filter: {reference_system} / "
            f"{max_distance_ly:g} LY max"
        )

    bodies_by_system = {}
    unresolved = []

    if hp_enabled:
        bodies_by_system, unresolved = engine.query_all_systems(
            systems,
            cancel_event=cancel_event,
        )
        engine.check_cancel(cancel_event)

    hotspot_filtered = []
    hotspot_clean = []
    planet_filtered = []
    planet_clean = []

    if config["hotspots_enabled"]:
        hotspot_raw = engine.build_hotspot_rows(
            systems,
            bodies_by_system,
            unresolved,
        )

        hotspot_filtered = engine.filter_hotspot_rows(
            systems,
            hotspot_raw,
            config["ring_types"],
            config["materials"],
            config["only_pristine"],
        )

        hotspot_clean = engine.clean_hotspot_rows(hotspot_filtered)

    if config["planets_enabled"]:
        planet_raw = engine.build_planet_rows(
            systems,
            bodies_by_system,
            unresolved,
        )

        planet_filtered = engine.filter_planet_rows(
            systems,
            planet_raw,
            config["only_landables"],
            config["planet_types"],
        )

        planet_clean = engine.clean_planet_rows(planet_filtered)

    hotspot_headers = list(engine.HOTSPOT_HEADERS)
    planet_headers = list(engine.PLANET_HEADERS)
    community_headers = list(community_deposits.COMMUNITY_HEADERS)
    community_rows = []
    community_systems = []
    community_distances = {}

    if config["community_deposits_enabled"]:
        if hp_enabled:
            (
                community_headers,
                community_rows,
                community_systems,
                community_distances,
            ) = _load_community_results(
                config,
                shared_systems=systems,
                shared_distances=system_distances,
                cancel_event=cancel_event,
            )
        else:
            (
                community_headers,
                community_rows,
                community_systems,
                community_distances,
            ) = _load_community_results(
                config,
                cancel_event=cancel_event,
            )
            systems = community_systems
            system_distances = community_distances

    show_reference_distance = bool(reference_system)
    if show_reference_distance:
        if config["hotspots_enabled"]:
            hotspot_headers, hotspot_clean = _add_distance_column(
                hotspot_headers,
                hotspot_clean,
                system_distances,
            )
        if config["planets_enabled"]:
            planet_headers, planet_clean = _add_distance_column(
                planet_headers,
                planet_clean,
                system_distances,
            )
        if config["community_deposits_enabled"]:
            community_headers, community_rows = _add_distance_column(
                community_headers,
                community_rows,
                community_distances or system_distances,
            )

    # Keep a compact Systems result alongside every scan output. This is the
    # resolved candidate set used by Hotspots/Planets, or the effective
    # database-system set for Community-only scans.
    system_metadata = system_filter_search.enrich_system_metadata(
        systems,
        system_metadata,
        cancel_event=cancel_event,
    )
    system_headers, system_rows = _build_system_results(
        systems,
        system_distances,
        system_metadata,
        show_reference_distance,
    )

    summary_config = dict(config)
    summary_config["systems"] = systems
    summary = engine.build_summary(
        summary_config,
        hotspot_filtered,
        planet_filtered,
        unresolved,
    )
    summary["community_deposits_enabled"] = config[
        "community_deposits_enabled"
    ]
    summary["community_deposits_found"] = len(community_rows)
    summary["reference_system"] = reference_system
    summary["max_distance_ly"] = max_distance_ly if reference_system else None

    return {
        "status": "COMPLETED",
        "systems": systems,
        "system_headers": system_headers,
        "system_rows": system_rows,
        "hotspot_headers": hotspot_headers,
        "hotspot_rows": hotspot_clean,
        "planet_headers": planet_headers,
        "planet_rows": planet_clean,
        "community_headers": community_headers,
        "community_rows": community_rows,
        "unresolved": unresolved,
        "summary": summary,
    }
