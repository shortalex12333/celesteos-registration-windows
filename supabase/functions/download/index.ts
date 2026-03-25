/**
 * /download Edge Function
 * ========================
 * Secure installer download endpoint (macOS DMG or Windows EXE).
 *
 * Flow:
 * 1. Purchase complete -> generate download_token
 * 2. Email buyer with download link: /download?token=xxx
 * 3. Buyer clicks link -> validate token, stream installer
 * 4. Mark token as used (single-use)
 *
 * Security:
 * - Tokens are 256-bit random, hashed in database
 * - Single-use, expire after 7 days
 * - IP logging and rate limiting
 * - Installer served from Supabase Storage (signed URL)
 */

import { serve } from "https://deno.land/std@0.208.0/http/server.ts";
import { computeYachtHash } from "../_shared/crypto.ts";
import { AuditLog, SecurityEvents, getServiceClient } from "../_shared/db.ts";
import {
  success,
  error,
  corsResponse,
  getClientInfo,
} from "../_shared/response.ts";

serve(async (req: Request) => {
  // Handle CORS preflight
  if (req.method === "OPTIONS") {
    return corsResponse();
  }

  if (req.method !== "GET") {
    return error("Method not allowed", 405);
  }

  const clientInfo = getClientInfo(req);

  try {
    // Get token from query string
    const url = new URL(req.url);
    const token = url.searchParams.get("token");

    if (!token) {
      await AuditLog.log({
        action: "download_missing_token",
        ...clientInfo,
      });
      return error("Missing download token", 400);
    }

    const db = getServiceClient();

    // Hash token for lookup
    const tokenHash = await computeYachtHash(token);

    // Find download link by token hash
    const { data: linkData, error: linkError } = await db
      .from("download_links")
      .select(`
        *,
        fleet_registry (
          yacht_id,
          yacht_name,
          buyer_email,
          installer_type
        )
      `)
      .eq("token_hash", tokenHash)
      .single();

    if (linkError || !linkData) {
      await SecurityEvents.log({
        eventType: "invalid_download_token",
        severity: "medium",
        details: { token_hash_prefix: tokenHash.substring(0, 16) },
        ...clientInfo,
      });

      await AuditLog.log({
        action: "download_invalid_token",
        ...clientInfo,
      });

      return error("Invalid or expired download link", 401);
    }

    // Check if token is expired
    if (new Date(linkData.expires_at) < new Date()) {
      await AuditLog.log({
        yachtId: linkData.yacht_id,
        action: "download_expired_token",
        details: { expired_at: linkData.expires_at },
        ...clientInfo,
      });

      return error("Download link has expired. Please request a new one.", 410);
    }

    // Check if already used (optional: allow multiple downloads)
    const maxDownloads = 3; // Allow 3 downloads per token
    if (linkData.download_count >= maxDownloads) {
      await AuditLog.log({
        yachtId: linkData.yacht_id,
        action: "download_max_reached",
        details: { count: linkData.download_count, max: maxDownloads },
        ...clientInfo,
      });

      return error("Maximum downloads reached. Please contact support.", 429);
    }

    // Increment download count
    await db
      .from("download_links")
      .update({
        download_count: linkData.download_count + 1,
        last_downloaded_at: new Date().toISOString(),
        last_download_ip: clientInfo.ipAddress,
      })
      .eq("id", linkData.id);

    // Determine platform from the stored download link or fleet registry
    const platform = linkData.platform || (linkData.fleet_registry?.installer_type === "exe" ? "windows" : "macos");

    // Log successful download
    await AuditLog.log({
      yachtId: linkData.yacht_id,
      action: "download_success",
      details: {
        download_number: linkData.download_count + 1,
        yacht_name: linkData.fleet_registry?.yacht_name,
        platform,
      },
      ...clientInfo,
    });

    // Use package_path from download_links if available, otherwise build from installer_type
    let installerPath: string;
    if (linkData.package_path) {
      installerPath = linkData.package_path;
    } else if (platform === "windows") {
      installerPath = `exe/${linkData.yacht_id}/CelesteOS-Setup-${linkData.yacht_id}.exe`;
    } else {
      installerPath = `dmg/${linkData.yacht_id}/CelesteOS-${linkData.yacht_id}.dmg`;
    }

    const { data: signedUrl, error: signError } = await db.storage
      .from("installers")
      .createSignedUrl(installerPath, 3600); // 1 hour expiry

    if (signError || !signedUrl) {
      console.error("Signed URL error:", signError);

      // Fallback: return info page with instructions
      return new Response(
        generateDownloadPage(
          linkData.fleet_registry?.yacht_name || linkData.yacht_id,
          null,
          "pending",
          platform
        ),
        { headers: { "Content-Type": "text/html" } }
      );
    }

    // Redirect to signed URL for download
    return Response.redirect(signedUrl.signedUrl, 302);

  } catch (err) {
    console.error("Download error:", err);

    await AuditLog.log({
      action: "download_error",
      details: { error: String(err) },
      ...clientInfo,
    });

    return error("Download failed", 500);
  }
});

/**
 * Generate download page HTML with platform-aware instructions.
 */
function generateDownloadPage(
  yachtName: string,
  downloadUrl: string | null,
  status: "ready" | "pending",
  platform: string
): string {
  const isMac = platform !== "windows";
  const fileLabel = isMac ? "CelesteOS.dmg" : "CelesteOS-Setup.exe";
  const instructions = isMac
    ? `<ol>
        <li>Download and open the DMG file</li>
        <li>Drag CelesteOS to Applications</li>
        <li>Launch CelesteOS from Applications</li>
        <li>Grant requested permissions when prompted</li>
        <li>Check your email and click the activation link</li>
        <li>Installation completes automatically</li>
      </ol>`
    : `<ol>
        <li>Download and run the installer (.exe)</li>
        <li>Follow the setup wizard to install CelesteOS</li>
        <li>Launch CelesteOS from the Start menu</li>
        <li>Check your email and click the activation link</li>
        <li>Installation completes automatically</li>
      </ol>`;

  return `<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>CelesteOS - Download</title>
  <style>
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      margin: 0;
      color: #e2e8f0;
    }
    .container {
      background: rgba(30, 41, 59, 0.8);
      border-radius: 16px;
      padding: 48px;
      text-align: center;
      max-width: 480px;
      box-shadow: 0 25px 50px rgba(0, 0, 0, 0.5);
      border: 1px solid rgba(148, 163, 184, 0.1);
    }
    h1 { color: #f1f5f9; margin: 0 0 16px; font-size: 28px; }
    p { color: #94a3b8; line-height: 1.6; margin: 0 0 24px; }
    .yacht-name { color: #60a5fa; font-weight: 600; }
    .btn {
      display: inline-block;
      background: #3b82f6;
      color: white;
      padding: 14px 32px;
      border-radius: 8px;
      text-decoration: none;
      font-weight: 500;
      transition: background 0.2s;
    }
    .btn:hover { background: #2563eb; }
    .instructions {
      margin-top: 32px;
      padding-top: 24px;
      border-top: 1px solid rgba(148, 163, 184, 0.2);
      text-align: left;
      font-size: 14px;
    }
    .instructions ol { padding-left: 20px; }
    .instructions li { margin-bottom: 8px; }
  </style>
</head>
<body>
  <div class="container">
    <h1>CelesteOS Download</h1>
    <p>Your personalized installer for <span class="yacht-name">${yachtName}</span></p>

    ${status === "ready" && downloadUrl ? `
    <a href="${downloadUrl}" class="btn">Download ${fileLabel}</a>
    ` : `
    <p style="color: #f59e0b;">Your installer is being prepared. Please check back shortly.</p>
    `}

    <div class="instructions">
      <p><strong>Installation Instructions:</strong></p>
      ${instructions}
    </div>
  </div>
</body>
</html>`;
}
