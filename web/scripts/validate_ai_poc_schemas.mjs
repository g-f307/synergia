#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const schemaDirectory = path.join(root, "docs", "schemas");
const schemaFiles = [
  "ai-quality-diagnosis-input.schema.json",
  "ai-quality-diagnosis-output.schema.json",
  "ai-operational-summary-input.schema.json",
  "ai-operational-summary-output.schema.json",
];

const ajv = new Ajv2020({ strict: true });
addFormats(ajv);

for (const filename of schemaFiles) {
  const schema = JSON.parse(
    fs.readFileSync(path.join(schemaDirectory, filename), "utf8"),
  );
  ajv.compile(schema);
  console.log(`AJV strict: ${filename}`);
}
