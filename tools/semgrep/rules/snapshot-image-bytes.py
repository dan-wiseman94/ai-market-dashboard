# Test fixture for snapshot-image-bytes-direct-read. Run: semgrep --test --config <dir>
def _fixture(img, image, snapshot_image, value, payload, read_image_bytes):
    # ruleid: snapshot-image-bytes-direct-read
    a = bytes(img.data)
    # ruleid: snapshot-image-bytes-direct-read
    b = bytes(image.data)
    # ruleid: snapshot-image-bytes-direct-read
    c = bytes(snapshot_image.data)
    # ok: snapshot-image-bytes-direct-read
    d = read_image_bytes(img)
    # ok: snapshot-image-bytes-direct-read
    e = bytes(value.data)
    # ok: snapshot-image-bytes-direct-read
    g = bytes(payload)
    return a, b, c, d, e, g
