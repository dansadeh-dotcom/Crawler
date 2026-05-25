#!/usr/bin/env node

/**
 * blob-upload.js
 * Uploads crawled JSONL files to Vercel Blob storage using @vercel/blob SDK.
 * Called by run.py after crawling completes.
 */

const fs = require("fs");
const path = require("path");
const { put, list } = require("@vercel/blob");

const BLOB_TOKEN = process.env.BLOB_READ_WRITE_TOKEN;
if (!BLOB_TOKEN) {
  console.error("❌ BLOB_READ_WRITE_TOKEN not set");
  process.exit(1);
}

const FOLDERS = [
  { local: "Android", blob: "Android" },
  { local: "iOS", blob: "iOS" },
  { local: "Desktop", blob: "Desktop" },
];

async function getExistingBlobs() {
  const existing = new Set();
  let cursor;
  do {
    const result = await list({ token: BLOB_TOKEN, limit: 1000, cursor });
    result.blobs.forEach(b => existing.add(b.pathname));
    cursor = result.hasMore ? result.cursor : undefined;
  } while (cursor);
  return existing;
}

async function uploadFolder(localFolder, blobFolder, existing) {
  const folderPath = path.join(process.cwd(), localFolder);

  if (!fs.existsSync(folderPath)) {
    console.log(`⏭️  ${localFolder} not found, skipping`);
    return;
  }

  const files = fs.readdirSync(folderPath)
    .filter(f => f.endsWith(".jsonl"))
    .sort()
    .reverse();

  if (files.length === 0) {
    console.log(`📁 ${localFolder}: no files to upload`);
    return;
  }

  const toUpload = files.filter(f => !existing.has(`${blobFolder}/${f}`));
  if (toUpload.length === 0) {
    console.log(`📁 ${localFolder}: all ${files.length} files already uploaded`);
    return;
  }

  console.log(`📁 ${localFolder}: uploading ${toUpload.length} new files (${files.length - toUpload.length} already exist)...`);

  for (const file of toUpload) {
    const localPath = path.join(folderPath, file);
    const blobPath = `${blobFolder}/${file}`;
    try {
      const content = fs.readFileSync(localPath);
      await put(blobPath, content, {
        access: "private",
        token: BLOB_TOKEN,
        addRandomSuffix: false,
        contentType: "text/plain",
      });
      console.log(`  ✅ ${blobPath}`);
    } catch (err) {
      console.log(`  ❌ ${file}: ${err.message}`);
    }
  }
}

async function main() {
  console.log("\n🚀 Uploading crawled files to Vercel Blob...\n");

  console.log("📋 Checking existing blobs...");
  const existing = await getExistingBlobs();
  console.log(`   Found ${existing.size} files already in storage.\n`);

  for (const { local, blob } of FOLDERS) {
    await uploadFolder(local, blob, existing);
  }

  console.log("\n✅ Blob upload complete\n");
}

main().catch(err => {
  console.error("❌ Error during upload:", err);
  process.exit(1);
});
