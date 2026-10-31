import test from "node:test";
import assert from "node:assert/strict";

import {
  initialProvenanceState,
  loadProvenanceRecord,
  provenanceQuery,
} from "./provenance.ts";

function jsonResponse(status: number, body: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  };
}

const cell = {
  recordId: "DrugComb:row-1",
  source: "DrugComb",
  sourceId: "row-1",
  metric: "ZIP",
  cellLine: "A549",
};

test("exact record identifiers are used when available", () => {
  assert.equal(provenanceQuery(cell), "record_id=DrugComb%3Arow-1");
  assert.equal(provenanceQuery({ source: "DrugComb", sourceId: "row-1" }), "source=DrugComb&source_id=row-1");
  assert.equal(provenanceQuery({ source: "DrugComb" }), null);
  assert.equal(provenanceQuery({}), null);
});

test("drawer starts in a loading state when an exact lookup is possible", () => {
  assert.deepEqual(initialProvenanceState(cell), { state: "loading" });
});

test("drawer states unavailable without a source identifier or record id", () => {
  const result = initialProvenanceState({ source: "DrugComb", metric: "ZIP" });
  assert.equal(result.state, "unavailable");
  assert.match(result.message, /no source identifier or record ID/i);
  const noSource = initialProvenanceState({ sourceId: "row-1" });
  assert.equal(noSource.state, "unavailable");
  assert.match(noSource.message, /no source label/i);
});

test("drawer loads exactly one stored record", async () => {
  let requested = "";
  const result = await loadProvenanceRecord(cell, {
    baseUrl: "http://api.test",
    fetchImpl: async url => {
      requested = url;
      return jsonResponse(200, {
        status: "found",
        record_id: "DrugComb:row-1",
        records: [{ record_id: "DrugComb:row-1", source: "DrugComb", source_id: "row-1", http_status: 200 }],
      });
    },
  });
  assert.equal(requested, "http://api.test/api/provenance/records?record_id=DrugComb%3Arow-1");
  assert.equal(result.state, "found");
  assert.equal(result.state === "found" && result.record.source_id, "row-1");
});

test("drawer reports an empty lookup without opening the ledger", async () => {
  const result = await loadProvenanceRecord(cell, {
    fetchImpl: async () => jsonResponse(404, { status: "not_found", records: [], reason: "No stored record." }),
  });
  assert.equal(result.state, "not_found");
  assert.match(result.message, /Provenance unavailable/);
  assert.equal("record" in result, false);
});

test("drawer reports an empty record list from a successful response", async () => {
  const result = await loadProvenanceRecord(cell, {
    fetchImpl: async () => jsonResponse(200, { status: "not_found", records: [] }),
  });
  assert.equal(result.state, "not_found");
});

test("drawer does not choose between ambiguous records", async () => {
  const result = await loadProvenanceRecord(cell, {
    fetchImpl: async () => jsonResponse(200, {
      status: "found",
      records: [{ record_id: "DrugComb:row-1" }, { record_id: "DrugComb:row-1@abc" }],
    }),
  });
  assert.equal(result.state, "not_found");
  assert.match(result.message, /multiple stored records/i);
});

test("drawer reports lookup errors distinctly from missing records", async () => {
  const httpFailure = await loadProvenanceRecord(cell, {
    fetchImpl: async () => jsonResponse(500, { status: "unavailable", records: [] }),
  });
  assert.equal(httpFailure.state, "error");
  assert.match(httpFailure.message, /HTTP 500/);

  const networkFailure = await loadProvenanceRecord(cell, {
    fetchImpl: async () => {
      throw new Error("connection refused");
    },
  });
  assert.equal(networkFailure.state, "error");
  assert.match(networkFailure.message, /could not be reached/);
});

test("drawer skips the request entirely without any identifier", async () => {
  let called = false;
  const result = await loadProvenanceRecord(
    { source: "DrugComb", metric: "ZIP" },
    {
      fetchImpl: async () => {
        called = true;
        return jsonResponse(200, { status: "found", records: [] });
      },
    },
  );
  assert.equal(called, false);
  assert.equal(result.state, "unavailable");
});
