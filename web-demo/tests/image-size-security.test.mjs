import assert from "node:assert/strict";
import test from "node:test";
import { Worker } from "node:worker_threads";

const workerSource = String.raw`
  const { parentPort, workerData } = require("node:worker_threads");
  (async () => {
    try {
      const module = await import(workerData.moduleName);
      module[workerData.exportName].calculate(Buffer.from(workerData.hex, "hex"));
      parentPort.postMessage("returned");
    } catch {
      parentPort.postMessage("rejected");
    }
  })();
`;

async function completesWithoutLoop(moduleName, exportName, hex) {
  const worker = new Worker(workerSource, {
    eval: true,
    workerData: { moduleName, exportName, hex },
  });
  let timeout;
  try {
    const result = await Promise.race([
      new Promise((resolve, reject) => {
        worker.once("message", resolve);
        worker.once("error", reject);
      }),
      new Promise((_, reject) => {
        timeout = setTimeout(() => reject(new Error("parser did not advance")), 1_000);
      }),
    ]);
    assert.match(result, /^(returned|rejected)$/);
  } finally {
    clearTimeout(timeout);
    await worker.terminate();
  }
}

test("ICNS parser advances past a zero-length entry", async () => {
  await completesWithoutLoop(
    "image-size/types/icns",
    "ICNS",
    "69636e73000000106963703400000000",
  );
});

test("JXL parser advances past a zero-length partial stream box", async () => {
  await completesWithoutLoop("image-size/types/jxl", "JXL", "000000006a786c70");
});

test("HEIF parser advances past a zero-length image-property box", async () => {
  await completesWithoutLoop(
    "image-size/types/heif",
    "HEIF",
    "000000406d6574610000000000000034697072700000002c6970636f0000000069737065000000000000000000000001000000010000000000000000",
  );
});
