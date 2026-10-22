import { expect } from '@playwright/test'
import { spawnSync } from 'node:child_process'

export interface SeedVerificationSnapshot {
  productCount: number
  productsOutsideColorRange: number
  productsMissingRequiredSizes: number
  negativeStockVariants: number
  duplicateProductSkus: number
  duplicateVariantSkus: number
  orphanVariants: number
}

const runConfiguredCommand = (variableName: string): void => {
  const serializedCommand = process.env[variableName]
  if (!serializedCommand) {
    throw new Error(`${variableName} chưa được cấu hình; backend chưa cung cấp reset/seed command.`)
  }

  let command: unknown
  try {
    command = JSON.parse(serializedCommand)
  } catch {
    throw new Error(`${variableName} phải là JSON array gồm executable và arguments.`)
  }
  if (!Array.isArray(command) || command.length === 0 || !command.every((item) => typeof item === 'string')) {
    throw new Error(`${variableName} phải là JSON array không rỗng và chỉ chứa string.`)
  }

  const [executable, ...args] = command
  const result = spawnSync(executable, args, {
    cwd: new URL('../..', import.meta.url),
    encoding: 'utf8',
    stdio: 'inherit',
  })
  if (result.status !== 0) throw new Error(`${variableName} thất bại với exit code ${result.status}`)
}

export const resetAndSeedDatabase = (): void => {
  if (process.env.QA_ALLOW_DB_RESET !== 'true') {
    throw new Error('Từ chối reset DB nếu QA_ALLOW_DB_RESET khác true.')
  }
  runConfiguredCommand('QA_DATABASE_RESET_COMMAND')
  runConfiguredCommand('QA_DATABASE_SEED_COMMAND')
}

export const expectValidSeedSnapshot = (snapshot: SeedVerificationSnapshot): void => {
  expect(snapshot.productCount).toBe(100)
  expect(snapshot.productsOutsideColorRange).toBe(0)
  expect(snapshot.productsMissingRequiredSizes).toBe(0)
  expect(snapshot.negativeStockVariants).toBe(0)
  expect(snapshot.duplicateProductSkus).toBe(0)
  expect(snapshot.duplicateVariantSkus).toBe(0)
  expect(snapshot.orphanVariants).toBe(0)
}
