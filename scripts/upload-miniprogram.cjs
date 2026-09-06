#!/usr/bin/env node

const fs = require('node:fs');
const path = require('node:path');
const ci = require('miniprogram-ci');

const repoRoot = path.resolve(__dirname, '..');
const projectPath = path.join(repoRoot, 'miniprogram');
const projectConfigPath = path.join(projectPath, 'project.config.json');

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, 'utf8'));
}

function env(name, fallback = '') {
  return process.env[name] || fallback;
}

function normalizePrivateKey() {
  const raw = env('WX_MINIPROGRAM_PRIVATE_KEY');
  const base64 = env('WX_MINIPROGRAM_PRIVATE_KEY_BASE64');

  if (raw) {
    return raw.includes('\\n') ? raw.replace(/\\n/g, '\n') : raw;
  }

  if (base64) {
    return Buffer.from(base64, 'base64').toString('utf8');
  }

  return '';
}

function uploadSetting(projectConfig) {
  const setting = projectConfig.setting || {};
  return {
    es6: setting.es6 !== false,
    minify: setting.minified !== false,
    minifyJS: setting.minified !== false,
    minifyWXML: setting.minifyWXML !== false,
    minifyWXSS: setting.minifyWXSS !== false,
    autoPrefixWXSS: true,
    uploadWithSourceMap: setting.uploadWithSourceMap !== false,
  };
}

async function main() {
  const projectConfig = readJson(projectConfigPath);
  const packageJson = readJson(path.join(repoRoot, 'package.json'));
  const appid = env('WX_MINIPROGRAM_APPID', projectConfig.appid);
  const robot = Number(env('WX_MINIPROGRAM_ROBOT', '1'));
  const version = env(
    'WX_MINIPROGRAM_VERSION',
    `${packageJson.version || '0.1.0'}-${env('GITHUB_RUN_NUMBER', 'local')}`,
  );
  const desc = env(
    'WX_MINIPROGRAM_UPLOAD_DESC',
    `CI upload ${env('GITHUB_SHA', 'local').slice(0, 12)}`,
  );
  const privateKey = normalizePrivateKey();
  const dryRun = process.argv.includes('--dry-run') || env('WX_MINIPROGRAM_DRY_RUN') === '1';

  if (!appid || !/^wx[a-f0-9]{16}$/i.test(appid)) {
    throw new Error(`Invalid miniprogram appid: ${appid || '(empty)'}`);
  }
  if (!Number.isInteger(robot) || robot < 1 || robot > 30) {
    throw new Error(`Invalid WX_MINIPROGRAM_ROBOT: ${robot}`);
  }
  if (!dryRun && !privateKey) {
    throw new Error('Missing WX_MINIPROGRAM_PRIVATE_KEY or WX_MINIPROGRAM_PRIVATE_KEY_BASE64');
  }

  console.log(JSON.stringify({
    appid,
    projectPath,
    robot,
    version,
    desc,
    dryRun,
  }, null, 2));

  if (dryRun) {
    console.log('Dry run passed. No upload was attempted.');
    return;
  }

  const project = new ci.Project({
    appid,
    type: 'miniProgram',
    projectPath,
    privateKey,
    ignores: [
      'node_modules/**/*',
      'project.private.config.json',
    ],
  });

  const result = await ci.upload({
    project,
    version,
    desc,
    robot,
    setting: uploadSetting(projectConfig),
    onProgressUpdate: console.log,
  });

  console.log('Upload finished.');
  console.log(JSON.stringify(result, null, 2));
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
