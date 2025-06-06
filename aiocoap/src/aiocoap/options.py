# SPDX-FileCopyrightText: Christian Amsüss and the aiocoap contributors
#
# SPDX-License-Identifier: MIT

from itertools import chain
from warnings import warn

from .numbers.optionnumbers import OptionNumber
from .error import UnparsableMessage


def _read_extended_field_value(value, rawdata):
    """Used to decode large values of option delta and option length
    from raw binary form."""
    if value >= 0 and value < 13:
        return (value, rawdata)
    elif value == 13:
        if len(rawdata) < 1:
            raise UnparsableMessage("Option ended prematurely")
        return (rawdata[0] + 13, rawdata[1:])
    elif value == 14:
        if len(rawdata) < 2:
            raise UnparsableMessage("Option ended prematurely")
        return (int.from_bytes(rawdata[:2], "big") + 269, rawdata[2:])
    else:
        raise UnparsableMessage("Option contained partial payload marker.")


def _write_extended_field_value(value):
    """Used to encode large values of option delta and option length
    into raw binary form.
    In CoAP option delta and length can be represented by a variable
    number of bytes depending on the value."""
    if value >= 0 and value < 13:
        return (value, b"")
    elif value >= 13 and value < 269:
        return (13, (value - 13).to_bytes(1, "big"))
    elif value >= 269 and value < 65804:
        return (14, (value - 269).to_bytes(2, "big"))
    else:
        raise ValueError("Value out of range.")


def _single_value_view(option_number, doc=None, deprecated=None):
    """Generate a property for a given option number, where the option is not
    repeatable. For getting, it will return the value of the first option
    object with matching number. For setting, it will remove all options with
    that number and create one with the given value. The property can be
    deleted, resulting in removal of the option from the header.

    For consistency, setting the value to None also clears the option. (Note
    that with the currently implemented optiontypes, None is not a valid value
    for any of them)."""

    def _getter(self, option_number=option_number):
        if deprecated is not None:
            warn(deprecated, stacklevel=2)
        options = self.get_option(option_number)
        if not options:
            return None
        else:
            return options[0].value

    def _setter(self, value, option_number=option_number):
        if deprecated is not None:
            # Stack level 3 is what it takes to get out of the typical
            # `Message(opt=val)` construction, and probably most useful.
            warn(deprecated, stacklevel=3)
        self.delete_option(option_number)
        if value is not None:
            self.add_option(option_number.create_option(value=value))

    def _deleter(self, option_number=option_number):
        if deprecated is not None:
            warn(deprecated, stacklevel=2)
        self.delete_option(option_number)

    return property(
        _getter,
        _setter,
        _deleter,
        doc or "Single-value view on the %s option." % option_number,
    )


def _items_view(option_number, doc=None):
    """Generate a property for a given option number, where the option is
    repeatable. For getting, it will return a tuple of the values of the option
    objects with matching number. For setting, it will remove all options with
    that number and create new ones from the given iterable."""

    def _getter(self, option_number=option_number):
        return tuple(o.value for o in self.get_option(option_number))

    def _setter(self, value, option_number=option_number):
        self.delete_option(option_number)
        for v in value:
            self.add_option(option_number.create_option(value=v))

    def _deleter(self, option_number=option_number):
        self.delete_option(option_number)

    return property(
        _getter,
        _setter,
        _deleter,
        doc=doc or "Iterable view on the %s option." % option_number,
    )


def _empty_presence_view(option_number, doc=None):
    """Generate a property for a given option number, where the option is not
    repeatable and (usually) empty. The values True and False are mapped to
    presence and absence of the option."""

    def _getter(self, option_number=option_number):
        return bool(self.get_option(option_number))

    def _setter(self, value, option_number=option_number):
        self.delete_option(option_number)
        if value:
            self.add_option(option_number.create_option())

    return property(
        _getter, _setter, doc=doc or "Presence of the %s option." % option_number
    )


class Options(object):
    """Represent CoAP Header Options."""

    # this is not so much an optimization as a safeguard -- if custom
    # attributes were placed here, they could be accessed but would not be
    # serialized
    __slots__ = ["_options"]

    def __init__(self):
        self._options = {}

    def __eq__(self, other):
        if not isinstance(other, Options):
            return NotImplemented
        # this implementation is much easier than implementing equality on
        # StringOption etc
        return self.encode() == other.encode()

    def __repr__(self):
        text = ", ".join(
            "%s: %s" % (OptionNumber(k), " / ".join(map(str, v)))
            for (k, v) in self._options.items()
        )
        return "<aiocoap.options.Options at %#x: %s>" % (id(self), text or "empty")

    def _repr_html_(self):
        if self._options:
            n_opt = sum(len(o) for o in self._options.values())
            items = (
                f'<li value="{int(k)}">{OptionNumber(k)._repr_html_()}: {", ".join(vi._repr_html_() for vi in v)}'
                for (k, v) in sorted(self._options.items())
            )
            return f"""<details><summary style="display:list-item">{n_opt} option{"s" if n_opt != 1 else ""}</summary><ol>{"".join(items)}</ol></details>"""
        else:
            return "<div>No options</div>"

    def decode(self, rawdata):
        """Passed a CoAP message body after the token as rawdata, fill self
        with the options starting at the beginning of rawdata, an return the
        rest of the message (the body)."""
        option_number = OptionNumber(0)

        while rawdata:
            if rawdata[0] == 0xFF:
                return rawdata[1:]
            dllen = rawdata[0]
            delta = (dllen & 0xF0) >> 4
            length = dllen & 0x0F
            rawdata = rawdata[1:]
            (delta, rawdata) = _read_extended_field_value(delta, rawdata)
            (length, rawdata) = _read_extended_field_value(length, rawdata)
            option_number += delta
            if len(rawdata) < length:
                raise UnparsableMessage("Option announced but absent")
            option = option_number.create_option(decode=rawdata[:length])
            self.add_option(option)
            rawdata = rawdata[length:]
        return b""

    def encode(self):
        """Encode all options in option header into string of bytes."""
        data = []
        current_opt_num = 0
        for option in self.option_list():
            optiondata = option.encode()

            delta, extended_delta = _write_extended_field_value(
                option.number - current_opt_num
            )
            length, extended_length = _write_extended_field_value(len(optiondata))

            data.append(bytes([((delta & 0x0F) << 4) + (length & 0x0F)]))
            data.append(extended_delta)
            data.append(extended_length)
            data.append(optiondata)

            current_opt_num = option.number

        return b"".join(data)

    def add_option(self, option):
        """Add option into option header."""
        self._options.setdefault(option.number, []).append(option)

    def delete_option(self, number):
        """Delete option from option header."""
        if number in self._options:
            self._options.pop(number)

    def get_option(self, number):
        """Get option with specified number."""
        return self._options.get(number, ())

    def option_list(self):
        return chain.from_iterable(
            sorted(self._options.values(), key=lambda x: x[0].number)
        )

    uri_path = _items_view(OptionNumber.URI_PATH)
    uri_query = _items_view(OptionNumber.URI_QUERY)
    location_path = _items_view(OptionNumber.LOCATION_PATH)
    location_query = _items_view(OptionNumber.LOCATION_QUERY)
    block2 = _single_value_view(OptionNumber.BLOCK2)
    block1 = _single_value_view(OptionNumber.BLOCK1)
    content_format = _single_value_view(OptionNumber.CONTENT_FORMAT)
    etag = _single_value_view(OptionNumber.ETAG, "Single ETag as used in responses")
    etags = _items_view(OptionNumber.ETAG, "List of ETags as used in requests")
    if_none_match = _empty_presence_view(OptionNumber.IF_NONE_MATCH)
    observe = _single_value_view(OptionNumber.OBSERVE)
    accept = _single_value_view(OptionNumber.ACCEPT)
    uri_host = _single_value_view(OptionNumber.URI_HOST)
    uri_port = _single_value_view(OptionNumber.URI_PORT)
    proxy_uri = _single_value_view(OptionNumber.PROXY_URI)
    proxy_scheme = _single_value_view(OptionNumber.PROXY_SCHEME)
    size1 = _single_value_view(OptionNumber.SIZE1)
    oscore = _single_value_view(OptionNumber.OSCORE)
    object_security = _single_value_view(
        OptionNumber.OSCORE, deprecated="Use `oscore` instead of `object_security`"
    )
    max_age = _single_value_view(OptionNumber.MAX_AGE)
    if_match = _items_view(OptionNumber.IF_MATCH)
    no_response = _single_value_view(OptionNumber.NO_RESPONSE)
    echo = _single_value_view(OptionNumber.ECHO)
    request_tag = _items_view(OptionNumber.REQUEST_TAG)
    hop_limit = _single_value_view(OptionNumber.HOP_LIMIT)
    request_hash = _single_value_view(
        OptionNumber.REQUEST_HASH,
        "Experimental property for draft-amsuess-core-cachable-oscore",
    )
    edhoc = _empty_presence_view(OptionNumber.EDHOC)
    size2 = _single_value_view(OptionNumber.SIZE2)
    # experimental for draft-gomez-core-coap-bp-03
    payload_length = _single_value_view(OptionNumber.PAYLOAD_LENGTH)
