from urllib.parse import urlparse, parse_qs


def normalize_multione_machine(
    serial,
    machine,
    drawings,
    base_url="https://b2b.multione-csf.com"
):
    normalized = {
        "manufacturer": "MULTIONE",
        "serial_number": serial,

        "model": {
            "external_id": str(
                machine.get("s_catalog_p_id")
            ),
            "model_number": machine.get(
                "p_code"
            ),
            "model_name": machine.get(
                "pd_name"
            )
        },

        "assemblies": []
    }

    for drawing in drawings:
        media = drawing.get(
            "media",
            [],
        )

        drawing_url = None

        if media:
            relative_url = media[0].get(
                "dm_url"
            )

            if relative_url:
                drawing_url = (
                    f"{base_url}{relative_url}"
                )

        assembly = {
            "external_id": str(
                drawing.get("d_id")
            ),
            "code": None,
            "name": drawing.get(
                "d_title"
            ),
            "description": drawing.get(
                "d_description"
            ),

            "serial_range": {
                "start": drawing.get(
                    "d_first_afterSales_s_no"
                ),
                "end": drawing.get(
                    "d_last_afterSales_s_no"
                )
            },

            "drawing": {
                "url": drawing_url,
                "url_type": "public",
                "expires_at": None
            },

            "parts": []
        }

        for component in drawing.get(
            "components",
            [],
        ):
            reference = component.get(
                "dc_reference"
            )

            for part in component.get(
                "parts",
                [],
            ):
                assembly["parts"].append({
                    "reference_number": reference,

                    "part_number": part.get(
                        "dcp_p_code"
                    ),

                    "description": part.get(
                        "dcp_p_description"
                    ),

                    "quantity": part.get(
                        "dcp_qta"
                    ),

                    "manufacturer_data": {
                        "preferred": part.get(
                            "dcp_preferred"
                        ),
                        "alternative": part.get(
                            "dcp_alternative"
                        ),
                        "disabled": part.get(
                            "dcp_disabled"
                        ),
                        "price": None,
                        "unit": None,
                        "note": None,
                        "info": None
                    }
                })

        normalized["assemblies"].append(
            assembly
        )

    return normalized


def normalize_peruzzo_machine(
    serial,
    machine,
    board_groups,
    parts_by_board
):
    normalized = {
        "manufacturer": "PERUZZO",
        "serial_number": serial,

        "model": {
            "external_id": str(
                machine.get("articleId")
            ),
            "model_number": machine.get(
                "articleCode"
            ),
            "model_name": machine.get(
                "articleName"
            )
        },

        "assemblies": []
    }

    for group in board_groups:
        serial_start = group.get("from")
        serial_end = group.get("to")

        for board in group.get(
            "boards",
            [],
        ):
            board_id = board.get("id")

            drawing_url = board.get(
                "imageUrl"
            )

            expires_at = None

            if drawing_url:
                query_params = parse_qs(
                    urlparse(
                        drawing_url
                    ).query
                )

                if (
                    "se" in query_params
                    and query_params["se"]
                ):
                    expires_at = (
                        query_params["se"][0]
                    )

            assembly = {
                "external_id": str(
                    board_id
                ),
                "code": board.get(
                    "code"
                ),
                "name": board.get(
                    "description"
                ),
                "description": board.get(
                    "description"
                ),

                "serial_range": {
                    "start": serial_start,
                    "end": serial_end
                },

                "drawing": {
                    "url": drawing_url,
                    "url_type": "temporary",
                    "expires_at": expires_at
                },

                "parts": []
            }

            parts = parts_by_board.get(
                board_id,
                [],
            )

            for part in parts:
                assembly["parts"].append({
                    "reference_number": (
                        part.get(
                            "positionOfBoard"
                        )
                    ),

                    "part_number": part.get(
                        "code"
                    ),

                    "description": (
                        part.get(
                            "description_EN"
                        )
                        or part.get(
                            "gridDescription"
                        )
                        or part.get(
                            "description"
                        )
                    ),

                    "quantity": part.get(
                        "quantity"
                    ),

                    "manufacturer_data": {
                        "preferred": None,
                        "alternative": None,
                        "disabled": None,
                        "price": part.get(
                            "price"
                        ),
                        "unit": part.get(
                            "um"
                        ),
                        "note": part.get(
                            "note"
                        ),
                        "info": part.get(
                            "info"
                        )
                    }
                })

            normalized["assemblies"].append(
                assembly
            )

    return normalized


def normalize_weidemann_machine(
    serial,
    sparepart_data,
    bom_tree,
):
    normalized = {
        "manufacturer": "WEIDEMANN",
        "serial_number": serial,

        "model": {
            "external_id": str(
                sparepart_data.get(
                    "productCode"
                )
            ),
            "model_number": (
                sparepart_data.get(
                    "productModel"
                )
            ),
            "model_name": (
                sparepart_data.get(
                    "productName"
                )
            )
        },

        "assemblies": []
    }

    def walk(value):
        if isinstance(value, dict):
            parts = value.get("parts")

            if isinstance(parts, list):
                drawing_file = value.get(
                    "drawing"
                )

                drawing_metadata_url = None

                if drawing_file:
                    drawing_metadata_url = (
                        "https://shop.weidemann-online.com"
                        "/ws/v2/pgk/machine/diagram/file/"
                        f"{drawing_file}"
                        "?lang=en&lang=en"
                    )

                assembly = {
                    "external_id": (
                        str(value.get("id"))
                        if value.get("id")
                        is not None
                        else None
                    ),

                    "code": (
                        str(
                            value.get(
                                "deviceNumber"
                            )
                        )
                        if value.get(
                            "deviceNumber"
                        )
                        is not None
                        else None
                    ),

                    "name": value.get(
                        "name"
                    ),

                    "description": (
                        value.get(
                            "displayDeviceComment"
                        )
                    ),

                    "serial_range": {
                        "start": None,
                        "end": None
                    },

                    "drawing": {
                        "url": drawing_metadata_url,
                        "url_type": (
                            "authenticated_metadata"
                            if drawing_metadata_url
                            else None
                        ),
                        "expires_at": None
                    },

                    "parts": []
                }

                for part in parts:
                    assembly["parts"].append({
                        "reference_number": (
                            part.get("pos")
                        ),

                        "part_number": (
                            str(
                                part.get("id")
                            )
                            if part.get("id")
                            is not None
                            else None
                        ),

                        "description": (
                            part.get(
                                "displayName"
                            )
                        ),

                        "quantity": (
                            part.get("qty")
                        ),

                        "manufacturer_data": {
                            "preferred": None,
                            "alternative": None,
                            "disabled": None,
                            "price": None,

                            "unit": part.get(
                                "unit"
                            ),

                            "note": part.get(
                                "itemnote"
                            ),

                            "info": part.get(
                                "displayPartNameComment"
                            ),

                            "measurement": (
                                part.get(
                                    "measurement"
                                )
                            ),

                            "standard": (
                                part.get(
                                    "standard"
                                )
                            ),

                            "wearpart": (
                                part.get(
                                    "wearpart"
                                )
                            ),

                            "nmFlb": part.get(
                                "nmFlb"
                            ),

                            "sealantNo": (
                                part.get(
                                    "sealantNo"
                                )
                            ),

                            "sealantcCode": (
                                part.get(
                                    "sealantcCode"
                                )
                            ),

                            "node": part.get(
                                "node"
                            ),

                            "sequence": part.get(
                                "sequence"
                            )
                        }
                    })

                normalized[
                    "assemblies"
                ].append(
                    assembly
                )

            for child in value.values():
                walk(child)

        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(bom_tree)

    return normalized