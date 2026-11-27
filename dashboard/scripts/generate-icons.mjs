import { deflateSync } from "node:zlib";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const outDir = join(root, "public", "icons");
mkdirSync(outDir, { recursive: true });

const CRC_TABLE = new Uint32Array(256);
for (let n = 0; n < 256; n += 1) {
  let c = n;
  for (let k = 0; k < 8; k += 1) {
    c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  }
  CRC_TABLE[n] = c >>> 0;
}

function crc32(buffer) {
  let crc = 0xffffffff;
  for (const byte of buffer) {
    crc = CRC_TABLE[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function chunk(type, data) {
  const typeBuffer = Buffer.from(type, "ascii");
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length, 0);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(Buffer.concat([typeBuffer, data])), 0);
  return Buffer.concat([length, typeBuffer, data, crc]);
}

function png(width, height, pixels) {
  const signature = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8;
  ihdr[9] = 2;
  ihdr[10] = 0;
  ihdr[11] = 0;
  ihdr[12] = 0;
  const raw = Buffer.alloc(height * (width * 3 + 1));
  for (let y = 0; y < height; y += 1) {
    const row = y * (width * 3 + 1);
    raw[row] = 0;
    for (let x = 0; x < width; x += 1) {
      const source = (y * width + x) * 3;
      raw[row + 1 + x * 3] = pixels[source];
      raw[row + 2 + x * 3] = pixels[source + 1];
      raw[row + 3 + x * 3] = pixels[source + 2];
    }
  }
  return Buffer.concat([
    signature,
    chunk("IHDR", ihdr),
    chunk("IDAT", deflateSync(raw, { level: 9 })),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

function mix(a, b, t) {
  return a + (b - a) * t;
}

function color(hex) {
  return [parseInt(hex.slice(1, 3), 16), parseInt(hex.slice(3, 5), 16), parseInt(hex.slice(5, 7), 16)];
}

const BG = color("#09090B");
const EMERALD = color("#10B981");
const WHITE = color("#F4F4F5");

function distanceToSegment(px, py, ax, ay, bx, by) {
  const dx = bx - ax;
  const dy = by - ay;
  const length = dx * dx + dy * dy || 1;
  const t = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / length));
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
}

function render(size) {
  const scale = 4;
  const high = size * scale;
  const pixels = new Uint8Array(size * size * 3);
  const center = high / 2;
  const ringRadius = high * 0.335;
  const ringWidth = high * 0.048;
  const linePoints = [
    [center - high * 0.155, center + high * 0.055],
    [center - high * 0.05, center - high * 0.055],
    [center + high * 0.045, center + high * 0.015],
    [center + high * 0.155, center - high * 0.14],
  ];
  const lineWidth = high * 0.017;
  const dotRadius = high * 0.025;

  for (let y = 0; y < size; y += 1) {
    for (let x = 0; x < size; x += 1) {
      let r = 0;
      let g = 0;
      let b = 0;
      for (let sy = 0; sy < scale; sy += 1) {
        for (let sx = 0; sx < scale; sx += 1) {
          const px = x * scale + sx + 0.5;
          const py = y * scale + sy + 0.5;
          let c = BG;
          const ringDistance = Math.abs(Math.hypot(px - center, py - center) - ringRadius);
          if (ringDistance <= ringWidth / 2) {
            c = EMERALD;
          }
          let lineDistance = Infinity;
          for (let index = 0; index < linePoints.length - 1; index += 1) {
            lineDistance = Math.min(
              lineDistance,
              distanceToSegment(
                px,
                py,
                linePoints[index][0],
                linePoints[index][1],
                linePoints[index + 1][0],
                linePoints[index + 1][1],
              ),
            );
          }
          if (lineDistance <= lineWidth / 2) {
            c = WHITE;
          }
          const [endX, endY] = linePoints[linePoints.length - 1];
          if (Math.hypot(px - endX, py - endY) <= dotRadius) {
            c = EMERALD;
          }
          r += c[0];
          g += c[1];
          b += c[2];
        }
      }
      const samples = scale * scale;
      const offset = (y * size + x) * 3;
      pixels[offset] = Math.round(r / samples);
      pixels[offset + 1] = Math.round(g / samples);
      pixels[offset + 2] = Math.round(b / samples);
    }
  }
  return png(size, size, pixels);
}

for (const [name, size] of [
  ["icon-192.png", 192],
  ["icon-512.png", 512],
  ["apple-touch-icon.png", 180],
  ["icon-32.png", 32],
]) {
  writeFileSync(join(outDir, name), render(size));
  console.log(`wrote ${name}`);
}

void mix;
