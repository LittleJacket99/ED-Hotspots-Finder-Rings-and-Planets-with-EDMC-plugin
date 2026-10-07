#!/usr/bin/env python3

"""System-search helper for the v8 local GUI.

This keeps the new Reference System / Max Distance behaviour isolated while
v8 functionality is still being completed. It reuses finder_engine's Spansh
request/retry helpers and can be consolidated into the core engine later.
"""

import math

import finder_engine as engine


DEFAULT_MAX_DISTANCE_LY = 50.0
MAX_ALLOWED_DISTANCE_LY = 300.0
SYSTEM_NAME_LOOKUP_URL = "https://spansh.co.uk/api/systems/field_values/system_names"
FACTION_LOOKUP_URL = (
    "https://spansh.co.uk/api/systems/field_values/"
    "autocomplete_controlling_minor_faction"
)


def _format_distance(value):
    return f"{float(value):g}"


def _validate_max_distance(value):
    try:
        distance = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Max Distance (LY) must be a number.") from exc

    if distance <= 0 or distance > MAX_ALLOWED_DISTANCE_LY:
        raise ValueError(
            "Max Distance (LY) must be greater than 0 and no more than 300."
        )
    return distance


def _lookup_system_record(system_name, *, cancel_event=None):
    """Return the exact Spansh field-value record for a system name.

    Matching is case-insensitive so user input such as ``mehit`` can be
    converted to Spansh's canonical ``Mehit`` spelling before systems/search.
    """

    engine.check_cancel(cancel_event)
    system_name = str(system_name or "").strip()
    if not system_name:
        raise ValueError("Reference System is required.")

    response = engine.request_with_retries(
        "GET",
        SYSTEM_NAME_LOOKUP_URL,
        cancel_event=cancel_event,
        params={"q": system_name},
        headers={
            "User-Agent": engine.USER_AGENT,
            "Accept": "application/json",
        },
    )
    data = response.json()
    candidates = data.get("min_max", []) or []
    wanted = engine.norm(system_name)

    for item in candidates:
        if engine.norm(item.get("name", "")) == wanted:
            return item

    raise ValueError(f'System not found on Spansh: "{system_name}".')


def canonicalize_system_name(system_name, *, cancel_event=None):
    """Return Spansh's canonical capitalization for an exact system name."""

    item = _lookup_system_record(system_name, cancel_event=cancel_event)
    canonical = str(item.get("name") or "").strip()
    if not canonical:
        raise ValueError(f'System not found on Spansh: "{system_name}".')
    return canonical


def canonicalize_faction_name(faction_name, *, cancel_event=None):
    """Return Spansh's canonical capitalization for an exact faction name.

    The autocomplete endpoint can return partial/fuzzy suggestions, so only a
    case-insensitive exact match is accepted. Similar names are never selected
    automatically.
    """

    engine.check_cancel(cancel_event)
    faction_name = str(faction_name or "").strip()
    if not faction_name:
        return ""

    response = engine.request_with_retries(
        "GET",
        FACTION_LOOKUP_URL,
        cancel_event=cancel_event,
        params={"q": faction_name},
        headers={
            "User-Agent": engine.USER_AGENT,
            "Accept": "application/json",
        },
    )
    data = response.json()
    values = data.get("values", []) or []
    wanted = engine.norm(faction_name)

    for value in values:
        canonical = str(value or "").strip()
        if canonical and engine.norm(canonical) == wanted:
            return canonical

    raise ValueError(f'Faction not found on Spansh: "{faction_name}".')


def _query_spansh_systems(
    filters,
    *,
    faction_name="",
    power_name="",
    power_match_field=None,
    selected_power_states=None,
    reference_system="",
    cancel_event=None,
):
    """Run one paginated Spansh systems/search query and return names/distances."""

    selected_power_states = list(selected_power_states or [])
    selected_state_keys = {engine.norm(state) for state in selected_power_states}

    systems = []
    distances = {}
    metadata = {}
    seen = set()
    page = 0

    while True:
        engine.check_cancel(cancel_event)

        payload = {
            "filters": dict(filters or {}),
            "size": engine.PAGE_SIZE,
            "page": page,
        }

        if reference_system:
            payload["reference_system"] = reference_system
            payload["sort"] = [
                {
                    "distance": {
                        "direction": "asc",
                    }
                }
            ]

        response = engine.request_with_retries(
            "POST",
            engine.SPANSH_SYSTEMS_URL,
            cancel_event=cancel_event,
            json=payload,
            headers={
                "User-Agent": engine.USER_AGENT,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        data = response.json()
        results = data.get("results", []) or []
        total = int(data.get("count", 0) or 0)

        for item in results:
            if faction_name and not engine.value_matches_exact(
                item.get("controlling_minor_faction", ""),
                faction_name,
            ):
                continue

            if power_name and power_match_field:
                if not engine.value_matches_exact(
                    item.get(power_match_field, []),
                    power_name,
                ):
                    continue

            if selected_state_keys:
                if engine.norm(item.get("power_state", "")) not in selected_state_keys:
                    continue

            system_name = str(
                item.get("name") or item.get("system_name") or ""
            ).strip()
            key = engine.norm(system_name)
            if not system_name or key in seen:
                continue

            seen.add(key)
            systems.append(system_name)

            if reference_system:
                try:
                    distances[key] = float(item.get("distance", ""))
                except (TypeError, ValueError):
                    pass

            metadata[key] = {
                "Population": item.get("population", ""),
                "Powerplay Progress": item.get("power_state_control_progress", ""),
            }

        if not results or (page + 1) * engine.PAGE_SIZE >= total:
            break

        page += 1
        engine.cancellable_sleep(engine.DELAY, cancel_event)

    return systems, distances, metadata


def search_systems_by_filters(
    faction_name,
    power_name,
    selected_power_states,
    *,
    reference_system="",
    max_distance_ly=DEFAULT_MAX_DISTANCE_LY,
    include_distances=False,
    cancel_event=None,
):
    faction_name = str(faction_name or "").strip()
    power_name = str(power_name or "").strip()
    reference_system = str(reference_system or "").strip()
    selected_power_states = [
        str(state).strip()
        for state in selected_power_states
        if str(state).strip()
    ]

    if faction_name:
        entered_faction = faction_name
        faction_name = canonicalize_faction_name(
            faction_name,
            cancel_event=cancel_event,
        )
        if faction_name != entered_faction:
            print(
                f'Faction normalized: "{entered_faction}" '
                f'-> "{faction_name}"'
            )

    if reference_system:
        max_distance_ly = _validate_max_distance(max_distance_ly)

        entered_reference = reference_system
        reference_system = canonicalize_system_name(
            reference_system,
            cancel_event=cancel_event,
        )
        if reference_system != entered_reference:
            print(
                f'Reference system normalized: "{entered_reference}" '
                f'-> "{reference_system}"'
            )

    if not faction_name and not power_name and not reference_system:
        return ([], {}) if include_distances else []

    print("Searching Spansh systems with filters:")
    if faction_name:
        print(f'  Controlling faction: "{faction_name}"')
    if power_name:
        print(f'  Power: "{power_name}"')
        print(
            "  Power states: "
            + (", ".join(selected_power_states) if selected_power_states else "ALL")
        )
    if reference_system:
        print(f'  Reference system: "{reference_system}"')
        print(f"  Max distance: {_format_distance(max_distance_ly)} LY")

    common_filters = {}

    # Spansh expects a scalar value for controlling_minor_faction. Sending a
    # one-item list here causes HTTP 400 when combined with reference filters.
    if faction_name:
        common_filters["controlling_minor_faction"] = {"value": faction_name}

    # Reference and distance are both handled server-side. Spansh returns the
    # distance field as well, so no per-system coordinate lookups are needed for
    # Systems / Hotspots / Planets resolution.
    if reference_system:
        common_filters["distance"] = {
            "min": "0",
            "max": _format_distance(max_distance_ly),
        }

    query_specs = []

    if power_name:
        if selected_power_states:
            unoccupied_selected = any(
                engine.norm(state) == engine.norm("Unoccupied")
                for state in selected_power_states
            )
            controlled_states = [
                state
                for state in selected_power_states
                if engine.norm(state) != engine.norm("Unoccupied")
            ]

            # Exploited/Fortified/Stronghold have an actual controller, so use
            # controlling_power rather than the broader `power` presence field.
            if controlled_states:
                filters = dict(common_filters)
                filters["controlling_power"] = {"value": [power_name]}
                filters["power_state"] = {"value": controlled_states}
                query_specs.append(
                    (
                        filters,
                        "controlling_power",
                        controlled_states,
                    )
                )

            # Unoccupied systems have controlling_power=None in Spansh, while
            # the selected power still appears in the `power` array. Query them
            # separately and union the results when mixed states are selected.
            if unoccupied_selected:
                filters = dict(common_filters)
                filters["power"] = {"value": [power_name]}
                filters["power_state"] = {"value": ["Unoccupied"]}
                query_specs.append(
                    (
                        filters,
                        "power",
                        ["Unoccupied"],
                    )
                )
        else:
            # With no Power State selected, preserve the broad Power meaning:
            # every system where the selected power is present/assigned.
            filters = dict(common_filters)
            filters["power"] = {"value": [power_name]}
            query_specs.append((filters, "power", []))
    else:
        query_specs.append((dict(common_filters), None, []))

    all_systems = []
    all_distances = {}
    all_metadata = {}
    seen = set()

    for filters, power_match_field, states_for_query in query_specs:
        systems, distances, metadata = _query_spansh_systems(
            filters,
            faction_name=faction_name,
            power_name=power_name,
            power_match_field=power_match_field,
            selected_power_states=states_for_query,
            reference_system=reference_system,
            cancel_event=cancel_event,
        )

        for system_name in systems:
            key = engine.norm(system_name)
            if key not in seen:
                seen.add(key)
                all_systems.append(system_name)
            if key in distances:
                all_distances[key] = distances[key]
            if key in metadata:
                all_metadata[key] = metadata[key]

    engine.check_cancel(cancel_event)

    if reference_system:
        all_systems.sort(
            key=lambda name: (
                all_distances.get(engine.norm(name), float("inf")),
                name.casefold(),
            )
        )
    else:
        all_systems.sort(key=str.casefold)

    print(f"Systems matching filters: {len(all_systems)}")

    if include_distances:
        return all_systems, all_distances, all_metadata
    return all_systems


def lookup_system_coordinates(system_name, *, cancel_event=None):
    """Return (x, y, z) for an exact system name using Spansh field values."""

    item = _lookup_system_record(system_name, cancel_event=cancel_event)
    canonical = str(item.get("name") or system_name).strip()
    try:
        return (
            float(item["x"]),
            float(item["y"]),
            float(item["z"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            f'Spansh returned invalid coordinates for "{canonical}".'
        ) from exc


def filter_systems_within_distance(
    reference_system,
    systems,
    *,
    max_distance_ly=DEFAULT_MAX_DISTANCE_LY,
    cancel_event=None,
):
    """Filter a small candidate set by true 3D distance from a reference.

    This remains useful for Community Deposits DB-first filtering, where the
    candidate set is already small and there is no reason to resolve the whole
    galaxy through a separate systems search.
    """

    reference_system = str(reference_system or "").strip()
    if not reference_system:
        return list(systems or []), {}

    max_distance_ly = _validate_max_distance(max_distance_ly)

    candidates = engine.deduplicate(systems or [])
    if not candidates:
        return [], {}

    entered_reference = reference_system
    reference_system = canonicalize_system_name(
        reference_system,
        cancel_event=cancel_event,
    )
    if reference_system != entered_reference:
        print(
            f'Reference system normalized: "{entered_reference}" '
            f'-> "{reference_system}"'
        )

    print("Filtering database systems by distance:")
    print(f'  Reference system: "{reference_system}"')
    print(f"  Max distance: {_format_distance(max_distance_ly)} LY")
    print(f"  Candidate database systems: {len(candidates)}")

    ref_x, ref_y, ref_z = lookup_system_coordinates(
        reference_system,
        cancel_event=cancel_event,
    )

    kept = []
    distances = {}
    for system in candidates:
        engine.check_cancel(cancel_event)
        key = engine.norm(system)

        if key == engine.norm(reference_system):
            distance = 0.0
        else:
            try:
                x, y, z = lookup_system_coordinates(
                    system,
                    cancel_event=cancel_event,
                )
            except ValueError as exc:
                print(f"Skipping database system {system}: {exc}")
                continue

            distance = math.sqrt(
                (x - ref_x) ** 2
                + (y - ref_y) ** 2
                + (z - ref_z) ** 2
            )

        if distance <= max_distance_ly:
            kept.append(system)
            distances[key] = distance

    kept.sort(key=str.casefold)
    print(f"Database systems within distance: {len(kept)}")
    return kept, distances
