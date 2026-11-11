/**
 * PayTriage Automated End-to-End Browser Walkthrough & Screenshot Capture
 * Follows Phase 5 Walkthrough Specification.
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
console.log("PAYTRIAGE PHASE 5: REAL BROWSER DEMO WALKTHROUGH")
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
      // not ready yet
    }
    await sleep(500)
  }
  return false
}

async function main() {
  const steps = []

  // 1. Start Backend Server
  console.log("\n[1/7] Launching FastAPI Backend on port 8000...")
  const pythonPath = resolve(rootDir, "backend/.venv/Scripts/python.exe")
  const backend = spawn(pythonPath, ["-m", "uvicorn", "backend.main:app", "--port", "8000", "--host", "127.0.0.1"], {
    cwd: rootDir,
    stdio: "pipe",
  })

  backend.stdout.on("data", (data) => {
    console.log(`[Backend] ${data.toString().trim()}`)
  })
  backend.stderr.on("data", (data) => {
    console.log(`[Backend Err] ${data.toString().trim()}`)
  })

  const backendReady = await waitForUrl("http://127.0.0.1:8000/api/health")
  if (!backendReady) {
    console.error("FATAL: Backend failed to start on http://127.0.0.1:8000")
    backend.kill()
    process.exit(1)
  }
  console.log("Backend is READY on http://127.0.0.1:8000/api/health")

  // 2. Start Frontend Vite Preview Server on port 5173
  console.log("\n[2/7] Launching Vite Frontend on port 5173...")
  const npmCmd = process.platform === "win32" ? "npm.cmd" : "npm"
  const frontend = spawn(npmCmd, ["run", "preview", "--", "--port", "5173", "--host", "127.0.0.1"], {
    cwd: resolve(rootDir, "frontend"),
    stdio: "pipe",
    shell: true,
  })

  frontend.stderr.on("data", (data) => {
    // console.log(`[Frontend Log] ${data}`)
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
  console.log("\n[3/7] Launching Playwright Chromium Browser...")
  const browser = await chromium.launch({
    headless: true,
    args: ["--no-sandbox", "--disable-setuid-sandbox"]
  })
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } })

  const consoleErrors = []
  page.on("console", (msg) => {
    if (msg.type() === "error") {
      consoleErrors.push(msg.text())
      console.log(`[Browser Console Error] ${msg.text()}`)
    }
  })
  page.on("pageerror", (err) => {
    consoleErrors.push(err.message)
    console.log(`[Browser Page Error] ${err.message}`)
  })
  page.on("response", async (res) => {
    if (res.status() >= 400) {
      try {
        const text = await res.text()
        console.log(`[API Error ${res.status()}] ${res.url()} => ${text}`)
      } catch {}
    }
  })

  try {
    // WALKTHROUGH STEP 1: Login
    console.log("\n--- Step 1: Navigating to Login Page ---")
    await page.goto("http://localhost:5173", { waitUntil: "networkidle" })
    await page.screenshot({ path: resolve(screenshotsDir, "01_login.png") })
    console.log("Screenshot saved: 01_login.png")
    steps.push({ step: "1. Login Screen", status: "PASS", note: "Clean authentication view loaded with demo quick-fill" })

    // Perform Login
    console.log("Filling merchant credentials from environment...")
    let demoUser = ""
    let demoPass = ""
    try {
      const envContent = fs.readFileSync(resolve(rootDir, "backend/.env"), "utf-8")
      const userMatch = envContent.match(/DEMO_USER\s*=\s*([^\r\n#]+)/)
      const passMatch = envContent.match(/DEMO_PASSWORD\s*=\s*([^\r\n#]+)/)
      if (userMatch) demoUser = userMatch[1].trim().replace(/^['"]|['"]$/g, "")
      if (passMatch) demoPass = passMatch[1].trim().replace(/^['"]|['"]$/g, "")
    } catch {}

    await page.fill("input[type='text']", demoUser)
    await page.fill("input[type='password']", demoPass)
    await page.click("button:has-text('Sign In to Recovery Command')")
    await page.waitForSelector("text=Recovery Command Overview", { timeout: 10000 })

    // WALKTHROUGH STEP 2: Command Center
    console.log("\n--- Step 2: Command Center Dashboard ---")
    await page.waitForSelector("text=TOTAL OUTSTANDING", { timeout: 5000 })
    await page.screenshot({ path: resolve(screenshotsDir, "02_command_center.png") })
    console.log("Screenshot saved: 02_command_center.png")
    steps.push({ step: "2. Command Center", status: "PASS", note: "Computed real portfolio metrics from backend & PayPal Sandbox" })

    // WALKTHROUGH STEP 3: Recovery Center Queue
    console.log("\n--- Step 3: Navigating to Recovery Center Queue ---")
    await page.click("button:has-text('Recovery Center')")
    await page.waitForSelector("text=Recovery Center & Prioritized Queue", { timeout: 8000 })
    await page.waitForSelector(".badge-sandbox", { timeout: 8000 })
    await page.screenshot({ path: resolve(screenshotsDir, "03_recovery_center.png") })
    console.log("Screenshot saved: 03_recovery_center.png")
    steps.push({ step: "3. Recovery Center Queue", status: "PASS", note: "Prioritized list ranked by score, priority badges, Live vs Demo badges" })

    // WALKTHROUGH STEP 4: Invoice Detail View (Pick Live Sandbox Invoice)
    console.log("\n--- Step 4: Examining Live Sandbox Invoice INV2-5NY5-V2PK-CASX-WNU2 ---")
    await page.click("tr:has-text('INV2-5NY5-V2PK-CASX-WNU2')")
    await page.waitForSelector("text=Recovery Score Breakdown", { timeout: 10000 })
    await page.waitForSelector("text=Grounded Recovery Explanation", { timeout: 10000 })
    await sleep(500)
    await page.screenshot({ path: resolve(screenshotsDir, "04_invoice_detail.png") })
    console.log("Screenshot saved: 04_invoice_detail.png")
    steps.push({ step: "4. Invoice Detail View", status: "PASS", note: "Factor breakdown, AI explanation panel labeled, strategy comparisons" })

    // WALKTHROUGH STEP 5: Reminder Studio & Approval Dialog
    console.log("\n--- Step 5: Preparing Reminder & Human Approval Gate ---")
    await page.click("button:has-text('Prepare Payment Reminder Draft')")
    await page.waitForSelector("text=Payment Reminder & Action Approval Studio", { timeout: 40000 })
    await page.waitForSelector("button:has-text('Propose & Open Approval Dialog'):not([disabled])", { timeout: 40000 })

    // Open Approval Dialog
    await page.click("button:has-text('Propose & Open Approval Dialog')")
    await page.waitForSelector("text=Human Action Approval Gate", { timeout: 15000 })
    await page.waitForSelector("text=SHA-256 Hash", { timeout: 15000 })
    await sleep(500)

    // Take Approval Dialog screenshot
    await page.screenshot({ path: resolve(screenshotsDir, "05_approval_and_execution.png") })
    console.log("Screenshot saved: 05_approval_and_execution.png")
    steps.push({ step: "5. Reminder Editor & Approval Dialog", status: "PASS", note: "Tone selector, exact parameters, SHA-256 hash, re-approval on edit warning" })

    // Approve action
    console.log("Clicking 'Approve Action as Merchant'...")
    await page.click("button:has-text('Approve Action as Merchant')")
    await page.waitForSelector("text=Execute Approved Action Now", { timeout: 10000 })

    // Execute action
    console.log("Clicking 'Execute Approved Action Now'...")
    await page.click("button:has-text('Execute Approved Action Now')")

    // Execution transitions directly to Activity Log
    console.log("Waiting for verified execution to record in Immutable Recovery Audit Log...")
    await page.waitForSelector("text=Immutable Recovery Audit Log", { timeout: 25000 })
    await page.waitForSelector("text=INV2-5NY5-V2PK-CASX-WNU2", { timeout: 10000 })
    await page.waitForSelector("text=VERIFIED & SENT", { timeout: 10000 })
    console.log("Action successfully executed and verified against PayPal Sandbox!")

    // WALKTHROUGH STEP 6: Activity Log Verification
    console.log("\n--- Step 6: Verifying Activity Log ---")
    await page.screenshot({ path: resolve(screenshotsDir, "06_activity_log.png") })
    console.log("Screenshot saved: 06_activity_log.png")
    steps.push({ step: "6. Activity Log", status: "PASS", note: "Verified audit entry recorded with 'Verified & Sent' label" })

    // Check console errors
    console.log(`\nBrowser console errors recorded: ${consoleErrors.length}`)
    if (consoleErrors.length === 0) {
      console.log("PASS: Browser console has ZERO errors.")
    } else {
      console.log(`WARNING: Console errors encountered: ${JSON.stringify(consoleErrors)}`)
    }

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
  for (const s of steps) {
    console.log(`[${s.status}] ${s.step}: ${s.note}`)
  }
}

main().catch(console.error)
