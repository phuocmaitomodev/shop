import { randomUUID } from 'node:crypto'
import { readdir, readFile, rm, stat } from 'node:fs/promises'
import { spawnSync } from 'node:child_process'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const qaRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const outputDir = join(qaRoot, 'test-results', `account-artifact-security-${process.pid}`)
const sentinel = `QaArtifactSentinel-${randomUUID()}`

const scanDirectory = async (directory) => {
  const leaks = []
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name)
    if (entry.isDirectory()) {
      leaks.push(...await scanDirectory(path))
      continue
    }
    if (!entry.isFile()) continue

    const contents = await readFile(path)
    if (contents.includes(Buffer.from(sentinel))) leaks.push(path)

    if (entry.name.endsWith('.zip')) {
      const archive = spawnSync('unzip', ['-p', path], { encoding: null, maxBuffer: 64 * 1024 * 1024 })
      if (archive.error) throw archive.error
      if (archive.status !== 0) throw new Error(`Không thể đọc archive ${path}`)
      if (archive.stdout.includes(Buffer.from(sentinel))) leaks.push(`${path} (archive content)`)
    }
  }
  return leaks
}

await rm(outputDir, { force: true, recursive: true })

const run = spawnSync(
  process.execPath,
  [
    'node_modules/@playwright/test/cli.js',
    'test',
    'tests/e2e/account.spec.ts',
    '--grep',
    '@account đăng nhập cookie',
    '--project=chromium-desktop',
    '--output',
    outputDir,
  ],
  {
    cwd: qaRoot,
    env: {
      ...process.env,
      QA_ACCOUNT_PASSWORD: sentinel,
      QA_ACCOUNT_COOKIE_NAME: `missing_cookie_${randomUUID()}`,
    },
    encoding: 'utf8',
    maxBuffer: 16 * 1024 * 1024,
  },
)

if (run.error) throw run.error
if (run.status === 0) {
  throw new Error('Lượt kiểm tra bảo mật phải thất bại có kiểm soát sau khi gửi mật khẩu')
}
const runOutput = `${run.stdout}\n${run.stderr}`
if (!runOutput.includes('accountCookie') && !runOutput.includes('toMatchObject')) {
  throw new Error('Lượt kiểm tra không thất bại tại assertion cookie được kiểm soát')
}

await stat(outputDir)
const leaks = await scanDirectory(outputDir)
if (leaks.length > 0) {
  throw new Error(`Phát hiện mật khẩu sentinel trong artifact: ${leaks.join(', ')}`)
}

const artifactNames = await readdir(outputDir, { recursive: true })
if (artifactNames.some((name) => name.endsWith('trace.zip'))) {
  throw new Error('Account failure vẫn giữ trace.zip có thể chứa request password')
}
if (!artifactNames.some((name) => name.endsWith('.png')) || !artifactNames.some((name) => name.endsWith('.webm'))) {
  throw new Error('Lượt kiểm tra phải giữ screenshot và video an toàn để kiểm chứng')
}

await rm(outputDir, { force: true, recursive: true })
console.log('PASS: controlled account failure retained safe screenshot/video and zero password sentinel occurrences')
