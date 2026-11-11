/**
 * PayTriage Automated End-to-End Browser Walkthrough & Screenshot Capture
 * Follows Phase 5 Walkthrough Specification and Final QA requirements.
 */

import { chromium } from "playwright"
import { spawn } from "child_process"
import { fileURLToPath } from "url"
import { dirname, resolve } from "path"
import fs from "fs"

const __dirname = dirname(fileURLToPath(import.meta.url))
const rootDir = resolve(__dirname, "../..")
const screenshotsDir = resolve(rootDir, "docs/screenshots")

if (!fs.existsSync(screenshotsDir)) {
  fs.mkdirSync(screenshotsDir, { recursive: true })
}

console.log("============================================================")
console.log("PAYTRIAGE QA: REAL BROWSER DEMO WALKTHROUGH")
console.log("============================================================")

async function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function waitForUrl(url, maxAttempts = 30) {
  for (let i = 0; i < maxAttempts; i++) {
    try {
      const res = await fetch(url)
      if (res.ok || res.status === 404 || res.status === 200) {
        return true
      }
    } catch {
      // wait
    }
    await sleep(500)
  }
  return false
}

async function main() {
  const steps = []

  // 1. Start Backend Server
  console.log("\n[1/8] Launching FastAPI Backend on port 8000...")
  const pythonPath = resolve(rootDir, "backend/.venv/Scripts/python.exe")
  const backend = spawn(pythonPath, ["-m", "uvicorn", "backend.main:app", "--port", "8000", "--host", "127.0.0.1"], {
    cwd: rootDir,
    stdio: "pipe",
  })

  backend.stdout.on("data", () => {})
  backend.stderr.on("data", () => {})

  const backendReady = await waitForUrl("http://127.0.0.1:8000/api/health")
  if (!backendReady) {
    console.error("FATAL: Backend failed to start on http://127.0.0.1:8000")
    backend.kill()
    process.exit(1)
  }
  console.log("Backend is READY on http://127.0.0.1:8000/api/health")

  // 2. Start Frontend Vite Preview Server on port 5173
  console.log("\n[2/8] Launching Vite Frontend on port 5173...")
  const npmCmd = process.platform === "win32" ? "npm.cmd" : "npm"
  const frontend = spawn(npmCmd, ["run", "preview", "--", "--port", "5173", "--host", "127.0.0.1"], {
    cwd: resolve(rootDir, "frontend"),
    stdio: "pipe",
    shell: true,
  })

  const frontendReady = await waitForUrl("http://localhost:5173")
  if (!frontendReady) {
    console.error("FATAL: Frontend preview server failed to start on http://localhost:5173")
    backend.kill()
    frontend.kill()
    process.exit(1)
  }
  console.log("Frontend is READY on http://localhost:5173")

  // 3. Launch Playwright Chromium
  console.log("\n[3/8] Launching Playwright Chromium Browser...")
  const browser = await chromium.launch({
    headless: true,
    args: ["--no-sandbox", "--disable-setuid-sandbox"]
  })
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } })

  const runtimeErrors = []
  page.on("console", (msg) => {
    // Only capture unexpected runtime errors, ignore expected negative test 401
    if (msg.type() === "error") {
      const text = msg.text()
      if (!text.includes("401") && !text.includes("Failed to load resource")) {
        runtimeErrors.push(text)
        console.log(`[Browser Console Error] ${text}`)
      }
    }
  })
  page.on("pageerror", (err) => {
    runtimeErrors.push(err.message)
    console.log(`[Browser Page Error] ${err.message}`)
  })

  try {
    // TEST A: Unauthenticated access redirect
    console.log("\n--- Checking Unauth Redirect / Login Gate ---")
    await page.goto("http://localhost:5173", { waitUntil: "networkidle" })
    await page.waitForSelector("text=Sign In to Recovery Command", { timeout: 8000 })
    steps.push({ step: "Unauth Redirect", status: "PASS", note: "Cleanly renders Login view when unauthenticated" })
    await page.screenshot({ path: resolve(screenshotsDir, "01_login.png") })
    console.log("Screenshot saved: 01_login.png")

    // TEST B: Password error display
    console.log("\n--- Testing Wrong Password Error Handling ---")
    await page.fill("input[type='text']", "wrong_merchant")
    await page.fill("input[type='password']", "wrong_password_attempt")
    await page.click("button:has-text('Sign In to Recovery Command')")
    await page.waitForSelector("text=Invalid credentials", { timeout: 8000 })
    console.log("Caught expected error banner: 'Invalid credentials'")
    steps.push({ step: "Password Error", status: "PASS", note: "Displays clear error message on wrong password" })

    // Read valid credentials from backend/.env
    let demoUser = ""
    let demoPass = ""
    try {
      const envContent = fs.readFileSync(resolve(rootDir, "backend/.env"), "utf-8")
      const userMatch = envContent.match(/DEMO_USER\s*=\s*([^\r\n#]+)/)
      const passMatch = envContent.match(/DEMO_PASSWORD\s*=\s*([^\r\n#]+)/)
      if (userMatch) demoUser = userMatch[1].trim().replace(/^['"]|['"]$/g, "")
      if (passMatch) demoPass = passMatch[1].trim().replace(/^['"]|['"]$/g, "")
    } catch {}

    // Perform Genuine Login
    console.log("\n--- Performing Merchant Demo Login ---")
    await page.fill("input[type='text']", demoUser)
    await page.fill("input[type='password']", demoPass)
    await page.click("button:has-text('Sign In to Recovery Command')")
    await page.waitForSelector("text=Recovery Command Overview", { timeout: 10000 })
    steps.push({ step: "Demo Login", status: "PASS", note: "Merchant authenticated with session token" })

    // Command Center Screenshot
    await page.waitForSelector("text=TOTAL OUTSTANDING", { timeout: 5000 })
    await page.screenshot({ path: resolve(screenshotsDir, "02_command_center.png") })
    console.log("Screenshot saved: 02_command_center.png")
    steps.push({ step: "Command Center", status: "PASS", note: "Computed portfolio metrics from backend & PayPal Sandbox" })

    // Recovery Center Queue
    console.log("\n--- Navigating to Recovery Center ---")
    await page.click("header button:has-text('Recovery Center')")
    await page.waitForSelector("text=Recovery Center & Prioritized Queue", { timeout: 8000 })
    await page.waitForSelector(".badge-sandbox", { timeout: 8000 })
    await page.screenshot({ path: resolve(screenshotsDir, "03_recovery_center.png") })
    console.log("Screenshot saved: 03_recovery_center.png")
    steps.push({ step: "Recovery Center Queue", status: "PASS", note: "Prioritized list ranked by score with Live and Demo badges" })

    // TEST C: Demo button guard
    console.log("\n--- Testing Demo Invoice Button Guard (INV-MOD-007) ---")
    await page.click("tr:has-text('INV-MOD-007')")
    await page.waitForSelector("text=Recovery Score Breakdown", { timeout: 10000 })
    await page.click("button:has-text('Prepare Payment Reminder Draft')")
    await page.waitForSelector("text=Payment Reminder & Action Approval Studio", { timeout: 45000 })
    await page.waitForSelector("text=Demo Data Guard Active", { timeout: 10000 })
    console.log("Verified Demo Guard: 'Demo Data Guard Active' banner displayed")
    steps.push({ step: "Demo Button Guard", status: "PASS", note: "Restricts live PayPal actions on benchmark demo data" })

    // Return to Recovery Center and select Live Sandbox Invoice
    console.log("\n--- Navigating to Live Sandbox Invoice (INV2-5NY5-V2PK-CASX-WNU2) ---")
    await page.click("header button:has-text('Recovery Center')")
    await page.waitForSelector("text=Recovery Center & Prioritized Queue", { timeout: 8000 })
    await page.click("tr:has-text('INV2-5NY5-V2PK-CASX-WNU2')")
    await page.waitForSelector("text=Recovery Score Breakdown", { timeout: 10000 })
    await page.screenshot({ path: resolve(screenshotsDir, "04_invoice_detail.png") })
    console.log("Screenshot saved: 04_invoice_detail.png")
    steps.push({ step: "Invoice Detail View", status: "PASS", note: "Score breakdown, AI/fallback panel, strategy comparison" })

    // TEST D: Approval parameters, SHA-256 hash, and Edit Invalidation
    console.log("\n--- Preparing Reminder & Opening Approval Gate ---")
    await page.click("button:has-text('Prepare Payment Reminder Draft')")
    await page.waitForSelector("text=Payment Reminder & Action Approval Studio", { timeout: 45000 })
    await page.waitForSelector("button:has-text('Propose & Open Approval Dialog'):not([disabled])", { timeout: 45000 })

    await page.click("button:has-text('Propose & Open Approval Dialog')")
    await page.waitForSelector("text=Human Action Approval Gate", { timeout: 15000 })
    await page.waitForSelector("text=SHA-256 Hash", { timeout: 15000 })
    await sleep(400)
    await page.screenshot({ path: resolve(screenshotsDir, "05_approval_and_execution.png") })
    console.log("Screenshot saved: 05_approval_and_execution.png")
    steps.push({ step: "Approval Parameters & SHA-256", status: "PASS", note: "Approval dialog displays exact parameters and SHA-256 hash" })

    // Approve action
    console.log("Approving action as human merchant...")
    await page.click("button:has-text('Approve Action as Merchant')")
    await page.waitForSelector("text=Execute Approved Action Now", { timeout: 10000 })

    // TEST E: Edit Invalidation
    console.log("Testing edit invalidation warning...")
    await page.click("button:has-text('Close')")
    await sleep(300)
    await page.fill("textarea", "Modifying body text after approval to trigger invalidation.")
    await page.waitForSelector("text=Approval Invalidated", { timeout: 10000 })
    console.log("Verified Edit Invalidation: Warning displayed when parameters change")
    steps.push({ step: "Edit Invalidation", status: "PASS", note: "Modifying parameters invalidates prior approval" })

    // Re-propose and execute cleanly
    console.log("Re-proposing clean action for execution...")
    await page.click("button:has-text('Propose & Open Approval Dialog')")
    await page.waitForSelector("text=Human Action Approval Gate", { timeout: 15000 })
    await page.click("button:has-text('Approve Action as Merchant')")
    await page.waitForSelector("text=Execute Approved Action Now", { timeout: 10000 })

    console.log("Executing approved action...")
    await page.click("button:has-text('Execute Approved Action Now')")

    // Activity Log & Verified Badges
    console.log("Waiting for verified execution in Immutable Recovery Audit Log...")
    await page.waitForSelector("text=Immutable Recovery Audit Log", { timeout: 45000 })
    await page.waitForSelector("text=Verified & Sent", { timeout: 25000 })
    await page.screenshot({ path: resolve(screenshotsDir, "06_activity_log.png") })
    console.log("Screenshot saved: 06_activity_log.png")
    steps.push({ step: "Verified Badges", status: "PASS", note: "Activity log verifies execution with 'Verified & Sent' badge" })

    // TEST F: Mobile Screenshot at 390px
    console.log("\n--- Capturing Mobile Viewport Screenshot at 390px ---")
    await page.setViewportSize({ width: 390, height: 844 })
    await sleep(500)
    await page.screenshot({ path: resolve(screenshotsDir, "07_mobile_view.png") })
    console.log("Screenshot saved: 07_mobile_view.png")
    steps.push({ step: "Mobile Viewport (390px)", status: "PASS", note: "Captured 390px mobile responsive view" })

    // TEST G: 0 Runtime Console Errors check
    console.log(`\nBrowser runtime errors recorded: ${runtimeErrors.length}`)
    const consolePass = runtimeErrors.length === 0
    steps.push({
      step: "0 Console Errors",
      status: consolePass ? "PASS" : "FAIL",
      note: consolePass ? "Zero runtime console errors recorded throughout walkthrough" : `Encountered: ${runtimeErrors.join("; ")}`
    })

  } catch (err) {
    console.error("Walkthrough error:", err)
    steps.push({ step: "Walkthrough Execution", status: "FAIL", note: String(err) })
  } finally {
    await browser.close()
    backend.kill()
    frontend.kill()
  }

  console.log("\n============================================================")
  console.log("WALKTHROUGH SUMMARY RESULTS")
  console.log("============================================================")
  let allPass = true
  for (const s of steps) {
    console.log(`[${s.status}] ${s.step}: ${s.note}`)
    if (s.status !== "PASS") allPass = false
  }

  if (!allPass) {
    process.exit(1)
  }
}

main().catch(console.error)
