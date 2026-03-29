import { describe, it, expect } from 'vitest'

describe('App', () => {
  it('should be importable', async () => {
    const mod = await import('../../src/App')
    expect(mod.default).toBeDefined()
  })
})
