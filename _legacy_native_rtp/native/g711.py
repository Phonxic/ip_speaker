BIAS = 0x84
CLIP = 32635
SEG_END = [0x1F, 0x3F, 0x7F, 0xFF, 0x1FF, 0x3FF, 0x7FF, 0xFFF]
ALAW_SEG_END = [0xFF, 0x1FF, 0x3FF, 0x7FF, 0xFFF, 0x1FFF, 0x3FFF, 0x7FFF]


def _clamp_sample(sample: int) -> int:
    return max(-32768, min(32767, int(sample)))


def _search_segment(value: int) -> int:
    for index, end in enumerate(SEG_END):
        if value <= end:
            return index
    return 8


def linear2ulaw(sample: int) -> int:
    sample = _clamp_sample(sample)
    if sample < 0:
        sample = BIAS - sample
        mask = 0x7F
    else:
        sample = BIAS + sample
        mask = 0xFF

    if sample > CLIP:
        sample = CLIP

    segment = _search_segment(sample >> 3)
    if segment >= 8:
        return 0x7F ^ mask

    ulaw = (segment << 4) | ((sample >> (segment + 3)) & 0x0F)
    return ulaw ^ mask


def encode_ulaw_frame(samples: list[int]) -> bytes:
    return bytes(linear2ulaw(sample) for sample in samples)



def linear2alaw(sample: int) -> int:
    sample = _clamp_sample(sample)
    if sample >= 0:
        mask = 0xD5
    else:
        mask = 0x55
        sample = -sample - 8
        if sample < 0:
            sample = 0

    if sample > 0x7FFF:
        sample = 0x7FFF

    segment = 0
    while segment < 8 and sample > ALAW_SEG_END[segment]:
        segment += 1
    if segment >= 8:
        return 0x7F ^ mask

    aval = segment << 4
    if segment < 2:
        aval |= (sample >> 4) & 0x0F
    else:
        aval |= (sample >> (segment + 3)) & 0x0F
    return aval ^ mask

def encode_alaw_frame(samples: list[int]) -> bytes:
    return bytes(linear2alaw(sample) for sample in samples)
