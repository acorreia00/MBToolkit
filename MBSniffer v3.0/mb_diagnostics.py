#!/usr/bin/env python3
"""Diagnostic helpers for MBSniffer traffic inspection and anomaly display."""

from mb_config import MODBUS_EXCEPTION_CODES, SLOW_RESPONSE_THRESHOLD_MS
from mb_protocol import crc16_modbus
from mb_i18n import LANGUAGE_PORTUGUESE, translate_details, translate_text


FUNCTION_NAMES = {
    0x01: "Read Coils",
    0x02: "Read Discrete Inputs",
    0x03: "Read Holding Registers",
    0x04: "Read Input Registers",
    0x05: "Write Single Coil",
    0x06: "Write Single Register",
    0x07: "Read Exception Status",
    0x08: "Diagnostics",
    0x0F: "Write Multiple Coils",
    0x10: "Write Multiple Registers",
    0x16: "Mask Write Register",
    0x17: "Read/Write Multiple Registers",
    0x2B: "Encapsulated Interface Transport",
}


def raw_hex_to_bytes(raw):
    try:
        return bytes.fromhex(str(raw or ""))
    except (TypeError, ValueError):
        return b""


def fc_number(record):
    text = str(record.get("fc", "") or "").strip()
    try:
        value = int(text, 16)
    except (TypeError, ValueError):
        return None
    if record.get("type") == "EXCEPTION":
        value &= 0x7F
    return value


def function_label(record, language=LANGUAGE_PORTUGUESE):
    fc = fc_number(record)
    if fc is None:
        return "—"
    name = FUNCTION_NAMES.get(fc, translate_text("Desconhecida/outra", language))
    return f"0x{fc:02X} — {name}"


def crc_fields(record):
    if str(record.get("type", "")).startswith("RAW"):
        return None, None, str(record.get("crc", "?"))

    frame = raw_hex_to_bytes(record.get("raw"))
    if len(frame) < 4:
        return None, None, str(record.get("crc", "?"))

    received = frame[-2] | (frame[-1] << 8)
    calculated = crc16_modbus(frame[:-2])
    return received, calculated, ("OK" if received == calculated else "ERROR")


def response_payload(record, language=LANGUAGE_PORTUGUESE):
    """Return (byte_count, data_hex, decoded_data) where available."""
    frame = raw_hex_to_bytes(record.get("raw"))
    if len(frame) < 3:
        return None, "", ""

    kind = str(record.get("type", ""))
    fc_raw = frame[1] if len(frame) >= 2 else 0
    fc = fc_raw & 0x7F

    if kind == "EXCEPTION":
        code = frame[2] if len(frame) >= 3 else None
        if code is None:
            return None, "", "Exception"
        info = MODBUS_EXCEPTION_CODES.get(code)
        name = info[0] if info else "Unknown/Reserved Exception"
        return None, "", f"0x{code:02X} — {name}"

    if kind == "RESPONSE" and fc in (1, 2, 3, 4) and len(frame) >= 5:
        byte_count = frame[2]
        data = frame[3:3 + byte_count]
        data_hex = " ".join(f"{b:02X}" for b in data)
        decoded = ""
        if fc in (3, 4) and byte_count % 2 == 0 and len(data) == byte_count:
            regs = [
                (data[i] << 8) | data[i + 1]
                for i in range(0, len(data), 2)
            ]
            decoded = translate_details(f"Registos={regs}", language)
        return byte_count, data_hex, decoded

    if kind == "REQUEST" and fc in (15, 16) and len(frame) >= 9:
        byte_count = frame[6]
        data = frame[7:7 + byte_count]
        return byte_count, " ".join(f"{b:02X}" for b in data), ""

    if kind == "REQUEST" and fc == 23 and len(frame) >= 13:
        byte_count = frame[10]
        data = frame[11:11 + byte_count]
        return byte_count, " ".join(f"{b:02X}" for b in data), ""

    return record.get("byte_count"), str(record.get("data_hex", "") or ""), ""


def anomaly_kind(record, threshold_ms=SLOW_RESPONSE_THRESHOLD_MS):
    """
    Return one anomaly class or None.

    Priority avoids ambiguous colouring when one frame satisfies several
    conditions. CRC is strongest because the frame itself is invalid.
    """
    if str(record.get("crc", "")) == "ERROR":
        return "crc"
    if bool(record.get("timed_out")):
        return "timeout"
    if str(record.get("type", "")) == "EXCEPTION":
        return "exception"
    if str(record.get("type", "")).startswith("RAW"):
        return "raw"

    try:
        response_ms = float(record.get("response_text", ""))
    except (TypeError, ValueError):
        response_ms = None

    if response_ms is not None and response_ms >= float(threshold_ms):
        return "slow"
    return None


RESULT_LABELS = {
    "success": ("✓ Sucesso", "Verde"),
    "slow": ("⚠ Resposta lenta", "Amarelo"),
    "exception": ("Exception", "Vermelho"),
    "crc": ("✕ CRC Error", "Vermelho"),
    "timeout": ("⚠ Timeout", "Laranja"),
    "raw": ("RAW", "Roxo"),
    "pending": ("Pendente / sem resultado", "Neutro"),
    "neutral": ("Sem classificação", "Neutro"),
}


def result_info(record, successful_request=False, language=LANGUAGE_PORTUGUESE):
    """
    Return (result_key, human_label, colour_name) for one traffic record.

    The semantic result is always available to the Frame Inspector. Whether
    the table/Inspector actually uses the category colour is controlled by
    "Realçar resultados".
    """
    if not record:
        return "neutral", "—", translate_text("Neutro", language)

    kind = anomaly_kind(record, SLOW_RESPONSE_THRESHOLD_MS)
    if kind:
        label, colour = RESULT_LABELS[kind]
        if kind == "raw":
            # Preserve the exact parser state in the Inspector.
            row_type = str(record.get("type", "RAW") or "RAW")
            label = row_type
        return kind, translate_text(label, language), translate_text(colour, language)

    row_type = str(record.get("type", ""))

    if (
        row_type == "RESPONSE"
        and record.get("crc") == "OK"
        and record.get("matched")
    ):
        label, colour = RESULT_LABELS["success"]
        return "success", translate_text(label, language), translate_text(colour, language)

    if row_type == "REQUEST":
        if successful_request and not record.get("timed_out"):
            label, colour = RESULT_LABELS["success"]
            return "success", translate_text(label, language), translate_text(colour, language)

        label, colour = RESULT_LABELS["pending"]
        return "pending", translate_text(label, language), translate_text(colour, language)

    label, colour = RESULT_LABELS["neutral"]
    return "neutral", translate_text(label, language), translate_text(colour, language)


def inspector_values(record, successful_request=False, language=LANGUAGE_PORTUGUESE):
    if not record:
        return {
            "slave": "Slave: —",
            "type": f"{translate_text('Tipo', language)}: —",
            "function": "Function: —",
            "response": "Resp.: —",
            "result": f"{translate_text('Resultado', language)}: —",
            "result_key": "neutral",
            "pdu": "PDU Address: —",
            "one_based": "1-based: —",
            "qty": "Qty: —",
            "byte_count": "ByteCount: —",
            "crc": "CRC: —",
            "data": f"{translate_text('Dados', language)}: —",
            "raw": "",
        }

    received, calculated, crc_state = crc_fields(record)
    if received is None:
        crc_text = f"CRC: {crc_state or '—'}"
    else:
        crc_text = (
            (f"CRC: received 0x{received:04X} / calculated 0x{calculated:04X} — {crc_state}" if language == "English" else f"CRC: recebido 0x{received:04X} / calculado 0x{calculated:04X} — {crc_state}")
        )

    byte_count, data_hex, decoded = response_payload(record, language=language)
    payload = decoded or data_hex or str(record.get("details", "") or "—")

    response = str(record.get("response_text", "") or "")
    if response:
        response += " ms"

    timeout_suffix = " — TIMEOUT" if record.get("timed_out") else ""
    result_key, result_label, _result_colour = result_info(
        record,
        successful_request=successful_request,
        language=language,
    )

    return {
        "slave": f"Slave: {record.get('slave') or '—'}",
        "type": f"{translate_text('Tipo', language)}: {record.get('type') or '—'}{timeout_suffix}",
        "function": f"Function: {function_label(record, language=language)}",
        "response": f"Resp.: {response or '—'}",
        "result": f"{translate_text('Resultado', language)}: {result_label}",
        "result_key": result_key,
        "pdu": f"PDU Address: {record.get('pdu_address') if record.get('pdu_address') is not None else '—'}",
        "one_based": f"1-based: {record.get('one_based') if record.get('one_based') is not None else '—'}",
        "qty": f"Qty: {record.get('qty') if record.get('qty') is not None else '—'}",
        "byte_count": f"ByteCount: {byte_count if byte_count is not None else '—'}",
        "crc": crc_text,
        "data": f"{translate_text('Dados', language)}: {translate_details(payload, language)}",
        "raw": str(record.get("raw", "") or ""),
    }


def decoded_record_text(record, successful_request=False, language=LANGUAGE_PORTUGUESE):
    values = inspector_values(
        record,
        successful_request=successful_request,
        language=language,
    )
    return "\n".join((
        values["slave"],
        values["type"],
        values["function"],
        values["response"],
        values["result"],
        values["pdu"],
        values["one_based"],
        values["qty"],
        values["byte_count"],
        values["crc"],
        values["data"],
        f"Raw: {values['raw']}",
    ))
