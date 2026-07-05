import http from "k6/http";
import { check, sleep } from "k6";
import { Counter, Rate, Trend } from "k6/metrics";

const BASE_URL = (__ENV.IPATLAS_BASE_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");
const PROFILE = __ENV.IPATLAS_PROFILE || "smoke";
const ENDPOINT = __ENV.IPATLAS_ENDPOINT || "mixed";
const BATCH_SIZE = intEnv("IPATLAS_BATCH_SIZE", 100, 1, 1000);
const PAGE_LIMIT = intEnv("IPATLAS_PAGE_LIMIT", 100, 1, 1000);
const SLEEP_SECONDS = floatEnv("IPATLAS_SLEEP_SECONDS", 0.1, 0, 60);
const WAIT_READY = boolEnv("IPATLAS_WAIT_READY", true);
const REQUIRE_PREFIX_LOADED = boolEnv("IPATLAS_REQUIRE_PREFIX_LOADED", true);
const WARM_CACHE = boolEnv("IPATLAS_WARM_CACHE", false);
const STRICT_THRESHOLDS = boolEnv("IPATLAS_STRICT_THRESHOLDS", false);
const CHECK_BODY = boolEnv("IPATLAS_CHECK_BODY", false);

const singleIpDuration = new Trend("ipatlas_single_ip_duration", true);
const batchDuration = new Trend("ipatlas_batch_duration", true);
const pagedDuration = new Trend("ipatlas_paged_duration", true);
const readyDuration = new Trend("ipatlas_ready_duration", true);
const responseBytes = new Counter("ipatlas_response_bytes");
const apiErrors = new Rate("ipatlas_api_errors");

const ips = loadSampleIps();
const asns = csvEnv("IPATLAS_ASNS", ["15169", "13335", "8075", "16509", "32934"]);
const cidrs = csvEnv("IPATLAS_CIDRS", [
  "1.1.1.0/24",
  "8.8.8.0/24",
  "34.102.0.0/16",
  "52.95.0.0/16",
  "140.82.112.0/20",
]);

export const options = {
  stages: profileStages(PROFILE),
  thresholds: thresholds(STRICT_THRESHOLDS),
  userAgent: "IPAtlas/k6-load-test",
};

export function setup() {
  if (WAIT_READY) {
    waitUntilReady();
  }
  if (WARM_CACHE) {
    warmLookupCache();
  }
  return {};
}

export default function () {
  if (ENDPOINT === "single") {
    lookupSingleIp(false);
  } else if (ENDPOINT === "single_sources") {
    lookupSingleIp(true);
  } else if (ENDPOINT === "batch") {
    lookupBatch();
  } else if (ENDPOINT === "paged") {
    lookupPaged();
  } else if (ENDPOINT === "health") {
    lookupReady();
  } else {
    lookupMixed();
  }
  sleep(SLEEP_SECONDS);
}

export function handleSummary(data) {
  const summary = {
    stdout: [
      "",
      "IPAtlas load test finished",
      `profile=${PROFILE}`,
      `endpoint=${ENDPOINT}`,
      `base_url=${BASE_URL}`,
      `qps_rps=${metricValue(data, "http_reqs", "rate")}`,
      `iterations_per_second=${metricValue(data, "iterations", "rate")}`,
      `http_req_failed=${metricValue(data, "http_req_failed", "rate")}`,
      `http_req_duration_p90=${metricValue(data, "http_req_duration", "p(90)")}`,
      `http_req_duration_p95=${metricValue(data, "http_req_duration", "p(95)")}`,
      `http_req_duration_p99=${metricValue(data, "http_req_duration", "p(99)")}`,
      `http_reqs=${metricValue(data, "http_reqs", "count")}`,
      "",
    ].join("\n"),
  };
  if (__ENV.IPATLAS_SUMMARY_JSON) {
    summary[__ENV.IPATLAS_SUMMARY_JSON] = JSON.stringify(data, null, 2);
  }
  return summary;
}

function lookupMixed() {
  const roll = Math.random();
  if (roll < 0.58) {
    lookupSingleIp(false);
  } else if (roll < 0.76) {
    lookupSingleIp(true);
  } else if (roll < 0.9) {
    lookupBatch();
  } else if (roll < 0.98) {
    lookupPaged();
  } else {
    lookupReady();
  }
}

function lookupSingleIp(includeSources) {
  const endpoint = includeSources ? "single_ip_sources" : "single_ip";
  const ip = pick(ips);
  const url = `${BASE_URL}/v1/ip/${encodeURIComponent(ip)}?include_sources=${includeSources}`;
  const res = http.get(url, { tags: { endpoint } });
  singleIpDuration.add(res.timings.duration, { endpoint });
  recordResponse(res, endpoint);
  assertOk(res, endpoint);
  if (CHECK_BODY && res.status === 200) {
    check(res, {
      [`${endpoint}: body has ip`]: (r) => Boolean(jsonField(safeJson(r), "ip")),
    });
  }
}

function lookupBatch() {
  const selectedIps = pickMany(ips, BATCH_SIZE);
  const payload = JSON.stringify({ ips: selectedIps, include_sources: false });
  const res = http.post(`${BASE_URL}/v1/ip/batch`, payload, {
    headers: { "content-type": "application/json" },
    tags: { endpoint: "batch" },
  });
  batchDuration.add(res.timings.duration, { endpoint: "batch", batch_size: String(BATCH_SIZE) });
  recordResponse(res, "batch");
  assertOk(res, "batch");
  if (CHECK_BODY && res.status === 200) {
    check(res, {
      "batch: count matches": (r) => jsonField(safeJson(r), "count") === BATCH_SIZE,
    });
  }
}

function lookupPaged() {
  if (Math.random() < 0.5) {
    const asn = pick(asns);
    const url = `${BASE_URL}/v1/asn/${asn}?limit=${PAGE_LIMIT}&offset=0`;
    const res = http.get(url, { tags: { endpoint: "asn" } });
    pagedDuration.add(res.timings.duration, { endpoint: "asn", limit: String(PAGE_LIMIT) });
    recordResponse(res, "asn");
    assertOk(res, "asn");
  } else {
    const cidr = pick(cidrs);
    const url = `${BASE_URL}/v1/cidr/${encodeURIComponent(cidr)}?limit=${PAGE_LIMIT}&offset=0`;
    const res = http.get(url, { tags: { endpoint: "cidr" } });
    pagedDuration.add(res.timings.duration, { endpoint: "cidr", limit: String(PAGE_LIMIT) });
    recordResponse(res, "cidr");
    assertOk(res, "cidr");
  }
}

function lookupReady() {
  const res = http.get(`${BASE_URL}/readyz`, { tags: { endpoint: "readyz" } });
  readyDuration.add(res.timings.duration, { endpoint: "readyz" });
  recordResponse(res, "readyz");
  assertOk(res, "readyz");
}

function waitUntilReady() {
  const timeoutSeconds = intEnv("IPATLAS_WAIT_READY_SECONDS", 180, 1, 3600);
  const deadline = Date.now() + timeoutSeconds * 1000;
  while (Date.now() < deadline) {
    const res = http.get(`${BASE_URL}/readyz`, { tags: { endpoint: "setup_readyz" } });
    if (res.status === 200) {
      const payload = safeJson(res);
      const prefixStatus = nestedField(payload, ["prefix_snapshots", "status"]);
      const indexOk = nestedField(payload, ["index", "ok"]) === true;
      if (indexOk && (!REQUIRE_PREFIX_LOADED || prefixStatus === "loaded")) {
        return;
      }
    }
    sleep(2);
  }
  throw new Error(`IPAtlas was not ready within ${timeoutSeconds}s`);
}

function warmLookupCache() {
  for (const ip of ips.slice(0, Math.min(ips.length, 100))) {
    http.get(`${BASE_URL}/v1/ip/${encodeURIComponent(ip)}?include_sources=false`, {
      tags: { endpoint: "warm_cache" },
    });
  }
}

function profileStages(profile) {
  if (profile === "baseline") {
    return [
      { duration: "30s", target: 50 },
      { duration: "2m", target: 50 },
      { duration: "30s", target: 0 },
    ];
  }
  if (profile === "stress") {
    return [
      { duration: "1m", target: 50 },
      { duration: "2m", target: 100 },
      { duration: "2m", target: 200 },
      { duration: "2m", target: 500 },
      { duration: "1m", target: 0 },
    ];
  }
  if (profile === "soak") {
    return [
      { duration: "1m", target: 100 },
      { duration: "30m", target: 100 },
      { duration: "1m", target: 0 },
    ];
  }
  return [
    { duration: "10s", target: 10 },
    { duration: "30s", target: 10 },
    { duration: "10s", target: 0 },
  ];
}

function thresholds(strict) {
  const base = {
    checks: ["rate>0.99"],
    http_req_failed: ["rate<0.01"],
    ipatlas_api_errors: ["rate<0.01"],
  };
  if (!strict) {
    return base;
  }
  return {
    ...base,
    "http_req_duration{endpoint:single_ip}": ["p(95)<30"],
    "http_req_duration{endpoint:single_ip_sources}": ["p(95)<60"],
    "http_req_duration{endpoint:batch}": ["p(95)<1000"],
    "http_req_duration{endpoint:asn}": ["p(95)<100"],
    "http_req_duration{endpoint:cidr}": ["p(95)<100"],
  };
}

function loadSampleIps() {
  const directIps = csvEnv("IPATLAS_SAMPLE_IPS", []);
  if (directIps.length > 0) {
    return directIps;
  }

  const sampleFile = __ENV.IPATLAS_SAMPLE_FILE || "tests/load/sample-ips.txt";
  try {
    const content = open(sampleFile);
    const fileIps = content
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter((line) => line && !line.startsWith("#"));
    if (fileIps.length > 0) {
      return fileIps;
    }
  } catch (error) {
    // Fall back to built-in samples when the script is run from another directory.
  }

  return [
    "8.8.8.8",
    "1.1.1.1",
    "114.114.114.114",
    "223.5.5.5",
    "208.67.222.222",
    "9.9.9.9",
    "104.16.132.229",
    "140.82.112.4",
    "34.102.136.180",
    "13.107.42.14",
    "2606:4700:4700::1111",
    "2001:4860:4860::8888",
  ];
}

function pick(values) {
  return values[Math.floor(Math.random() * values.length)];
}

function pickMany(values, count) {
  const selected = [];
  for (let index = 0; index < count; index += 1) {
    selected.push(pick(values));
  }
  return selected;
}

function recordResponse(res, endpoint) {
  apiErrors.add(res.status < 200 || res.status >= 400, { endpoint });
  responseBytes.add((res.body || "").length, { endpoint });
}

function assertOk(res, endpoint) {
  check(res, {
    [`${endpoint}: status is 200`]: (r) => r.status === 200,
  });
}

function safeJson(res) {
  try {
    return res.json();
  } catch (error) {
    return null;
  }
}

function jsonField(payload, field) {
  if (payload === null || typeof payload !== "object") {
    return undefined;
  }
  return payload[field];
}

function nestedField(payload, fields) {
  let current = payload;
  for (const field of fields) {
    if (current === null || typeof current !== "object") {
      return undefined;
    }
    current = current[field];
  }
  return current;
}

function csvEnv(name, fallback) {
  const value = __ENV[name];
  if (!value) {
    return fallback;
  }
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function boolEnv(name, fallback) {
  const value = __ENV[name];
  if (value === undefined || value === "") {
    return fallback;
  }
  return ["1", "true", "yes", "on"].includes(value.toLowerCase());
}

function intEnv(name, fallback, min, max) {
  const parsed = Number.parseInt(__ENV[name] || "", 10);
  if (Number.isNaN(parsed)) {
    return fallback;
  }
  return Math.min(max, Math.max(min, parsed));
}

function floatEnv(name, fallback, min, max) {
  const parsed = Number.parseFloat(__ENV[name] || "");
  if (Number.isNaN(parsed)) {
    return fallback;
  }
  return Math.min(max, Math.max(min, parsed));
}

function metricValue(data, metricName, key) {
  const metric = data.metrics && data.metrics[metricName];
  if (!metric) {
    return "n/a";
  }
  if (!metric.values || metric.values[key] === undefined) {
    return "n/a";
  }
  return metric.values[key];
}
