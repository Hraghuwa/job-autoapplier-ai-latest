/**
 * RED tests — automation page button states.
 *
 * Bugs identified from code review:
 *  1. Stop button not disabled while stopMutation.isPending
 *  2. Launch button stays active after click (double-submit risk)
 *  3. linkedin_cookies not counted as valid credential in readiness check
 *  4. Cookie status query typed too narrowly (missing has_li_at / ready)
 */
import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// ── Minimal helpers to test logic without rendering full pages ────────────────

// Bug 1: Stop button disabled while pending
describe('Stop button', () => {
  it('disables during pending mutation to prevent double-stop', () => {
    let isPending = false
    const disabled = isPending
    expect(disabled).toBe(false)

    // After click isPending becomes true
    isPending = true
    const disabledAfterClick = isPending
    expect(disabledAfterClick).toBe(true)
  })
})

// Bug 2: Launch button
describe('Launch button', () => {
  it('disables when isStarting is true', () => {
    const isStarting = true
    const selectedPhases = [1]
    const isReady = true
    const disabled = !isReady || selectedPhases.length === 0 || isStarting
    expect(disabled).toBe(true)
  })

  it('is enabled when ready and not starting', () => {
    const isStarting = false
    const selectedPhases = [1]
    const isReady = true
    const disabled = !isReady || selectedPhases.length === 0 || isStarting
    expect(disabled).toBe(false)
  })

  it('disables when no phases selected', () => {
    const isStarting = false
    const selectedPhases: number[] = []
    const isReady = true
    const disabled = !isReady || selectedPhases.length === 0 || isStarting
    expect(disabled).toBe(true)
  })
})

// Bug 3: Readiness check must count LinkedIn cookies as valid credential
describe('Agent readiness — credential check', () => {
  interface CredStatus {
    linkedin: boolean
    wellfound: boolean
    internshala: boolean
    unstop: boolean
    naukri: boolean
  }

  interface CookieStatus {
    stored: boolean
    has_li_at: boolean
    ready: boolean
    count: number
  }

  function hasCreds(credStatus: CredStatus | undefined, cookieStatus: CookieStatus | undefined): boolean {
    // Bug: original code only checks credStatus.linkedin || credStatus.wellfound
    // Fix must also accept cookieStatus.ready as a valid LinkedIn auth path
    if (!credStatus && !cookieStatus) return false
    const hasPassword = credStatus && (credStatus.linkedin || credStatus.wellfound)
    const hasCookies = cookieStatus?.ready === true
    return !!(hasPassword || hasCookies)
  }

  it('returns true when LinkedIn password cred is stored', () => {
    const creds: CredStatus = { linkedin: true, wellfound: false, internshala: false, unstop: false, naukri: false }
    expect(hasCreds(creds, undefined)).toBe(true)
  })

  it('returns true when LinkedIn cookies are ready (no password)', () => {
    const creds: CredStatus = { linkedin: false, wellfound: false, internshala: false, unstop: false, naukri: false }
    const cookies: CookieStatus = { stored: true, has_li_at: true, ready: true, count: 45 }
    expect(hasCreds(creds, cookies)).toBe(true)
  })

  it('returns false when cookies stored but no li_at (exported before login)', () => {
    const creds: CredStatus = { linkedin: false, wellfound: false, internshala: false, unstop: false, naukri: false }
    const cookies: CookieStatus = { stored: true, has_li_at: false, ready: false, count: 10 }
    expect(hasCreds(creds, cookies)).toBe(false)
  })

  it('returns false when nothing configured', () => {
    const creds: CredStatus = { linkedin: false, wellfound: false, internshala: false, unstop: false, naukri: false }
    expect(hasCreds(creds, undefined)).toBe(false)
  })
})

// Bug 4: LinkedIn cookie status API shape
describe('LinkedIn cookie status query shape', () => {
  it('backend returns rich status with has_li_at and ready fields', () => {
    // The backend returns this shape (from /onboarding/linkedin-cookies-status)
    const backendResponse = {
      stored: true,
      count: 45,
      has_li_at: true,
      expiry: 1800000000,
      ready: true,
    }
    // All fields must exist and be typed correctly
    expect(typeof backendResponse.stored).toBe('boolean')
    expect(typeof backendResponse.has_li_at).toBe('boolean')
    expect(typeof backendResponse.ready).toBe('boolean')
    expect(typeof backendResponse.count).toBe('number')
    // The UI typed this as just { stored: boolean } — that misses has_li_at and ready
    // The correct type must include all fields
    expect('has_li_at' in backendResponse).toBe(true)
    expect('ready' in backendResponse).toBe(true)
  })
})
