/**
 * LockTrace - Thirdweb Backend Engine & Server Wallet Integration
 * ==============================================================
 * Enables backend transaction execution, ERC1155 / ERC721 claiming,
 * ERC20 token transfers, and Engine transaction enqueuing.
 */

import {
  createThirdwebClient,
  sendTransaction,
  getContract,
  Engine,
  defineChain,
} from "thirdweb";
import {
  baseSepolia,
  base,
  ethereum,
  polygon,
  arbitrum,
  optimism,
  bsc,
} from "thirdweb/chains";
import { claimTo as claimToERC1155 } from "thirdweb/extensions/erc1155";
import { claimTo as claimToERC721 } from "thirdweb/extensions/erc721";
import { transfer as transferERC20 } from "thirdweb/extensions/erc20";
import { privateKeyToAccount } from "thirdweb/wallets";
import * as fs from "fs";
import * as path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Load environment variables from .env if present (Zero-dependency parser - REV7-01 Hardened)
const envPath = path.resolve(__dirname, ".env");
if (fs.existsSync(envPath)) {
  try {
    const envContent = fs.readFileSync(envPath, "utf-8");
    for (const line of envContent.split("\n")) {
      const trimmed = line.trim();
      if (trimmed && !trimmed.startsWith("#") && trimmed.includes("=")) {
        const [k, ...v] = trimmed.split("=");
        const key = k.trim();
        let val = v.join("=").trim();
        const quoteMatch = val.match(/^(['"])([\s\S]*?)\1(?:\s*#.*)?$/);
        if (quoteMatch) {
          val = quoteMatch[2];
        } else {
          val = val.split("#")[0].trim();
        }
        if (key && !process.env[key]) {
          process.env[key] = val;
        }
      }
    }
  } catch (e) {
    // ignore
  }
}

// Chain resolver
function resolveChain(chainIdentifier) {
  if (!chainIdentifier) return baseSepolia;
  const str = String(chainIdentifier).toLowerCase().trim();
  if (str === "base-sepolia" || str === "84532") return baseSepolia;
  if (str === "base" || str === "8453") return base;
  if (str === "ethereum" || str === "mainnet" || str === "1") return ethereum;
  if (str === "polygon" || str === "137") return polygon;
  if (str === "arbitrum" || str === "42161") return arbitrum;
  if (str === "optimism" || str === "10") return optimism;
  if (str === "bsc" || str === "56") return bsc;

  // Numeric chain ID fallback
  const num = parseInt(str, 10);
  if (!isNaN(num) && num > 0) {
    return defineChain(num);
  }
  return baseSepolia;
}

// Initialize Thirdweb Client with secret key
function getClient() {
  const secretKey = process.env.THIRDWEB_SECRET_KEY;
  if (!secretKey) {
    throw new Error("THIRDWEB_SECRET_KEY is not defined in environment");
  }
  return createThirdwebClient({ secretKey });
}

function isValidEvmAddress(address) {
  return typeof address === "string" && /^0x[a-fA-F0-9]{40}$/.test(address.trim());
}

function parseSafePositiveBigInt(val, fieldName = "value", allowZero = false) {
  if (val === undefined || val === null) {
    throw new Error(`Field '${fieldName}' is required`);
  }
  const strVal = String(val).trim();
  if (!/^\d+$/.test(strVal)) {
    throw new Error(`Field '${fieldName}' must be a non-negative integer`);
  }
  const big = BigInt(strVal);
  if (!allowZero && big <= 0n) {
    throw new Error(`Field '${fieldName}' must be greater than zero`);
  }
  return big;
}

/**
 * Mint or claim ERC1155 NFT to a user via Engine or Server Wallet
 */
export async function claimERC1155({
  contractAddress,
  chain = "base-sepolia",
  to,
  tokenId = 0,
  quantity = 1,
  serverWalletAddress,
}) {
  if (!isValidEvmAddress(contractAddress)) {
    throw new Error(`Invalid contract address: ${contractAddress}`);
  }
  if (!isValidEvmAddress(to)) {
    throw new Error(`Invalid recipient EVM address: ${to}`);
  }
  const safeTokenId = parseSafePositiveBigInt(tokenId, "tokenId", true);
  const safeQuantity = parseSafePositiveBigInt(quantity, "quantity", false);

  const client = getClient();
  const targetChain = resolveChain(chain);
  const targetWallet =
    serverWalletAddress || process.env.THIRDWEB_SERVER_WALLET_ADDRESS;

  const contract = getContract({
    client,
    address: contractAddress,
    chain: targetChain,
  });

  const transaction = claimToERC1155({
    contract,
    to,
    tokenId: safeTokenId,
    quantity: safeQuantity,
  });

  // If server wallet address is provided, use Engine.serverWallet
  if (targetWallet) {
    const serverWallet = Engine.serverWallet({
      client,
      address: targetWallet,
      ...(process.env.THIRDWEB_ENGINE_URL
        ? { engineUrl: process.env.THIRDWEB_ENGINE_URL }
        : {}),
    });

    const { transactionId } = await serverWallet.enqueueTransaction({
      transaction,
    });

    return {
      mode: "engine",
      transactionId,
      serverWalletAddress: targetWallet,
      contractAddress,
      to,
      tokenId: String(tokenId),
      quantity: String(quantity),
      chain: targetChain.id,
    };
  }

  // Fallback: If local server private key is configured
  if (process.env.THIRDWEB_SERVER_PRIVATE_KEY) {
    // AUD15-07: Normalize 0x prefix for Thirdweb private key to support both raw 64-hex and 0x formats
    let rawPk = process.env.THIRDWEB_SERVER_PRIVATE_KEY.trim();
    if (!rawPk.startsWith("0x") && !rawPk.startsWith("0X")) {
      rawPk = `0x${rawPk}`;
    }
    const account = privateKeyToAccount({
      client,
      privateKey: rawPk,
    });

    const result = await sendTransaction({
      account,
      transaction,
    });

    return {
      mode: "direct",
      transactionHash: result.transactionHash,
      contractAddress,
      to,
      tokenId: String(tokenId),
      quantity: String(quantity),
      chain: targetChain.id,
    };
  }

  throw new Error(
    "Neither THIRDWEB_SERVER_WALLET_ADDRESS (Engine) nor THIRDWEB_SERVER_PRIVATE_KEY is configured in .env"
  );
}

function isValidTransactionId(id) {
  // AUD15-07: Prevent CLI flag/option injection by disallowing leading hyphens
  return typeof id === "string" && /^[a-zA-Z0-9][a-zA-Z0-9_\-]{7,127}$/.test(id.trim());
}

/**
 * Check transaction status on Engine
 */
export async function getTransactionStatus(transactionId) {
  if (!isValidTransactionId(transactionId)) {
    throw new Error("Invalid transaction ID format");
  }
  const client = getClient();
  const executionResult = await Engine.getTransactionStatus({
    client,
    transactionId: transactionId.trim(),
  });
  return executionResult;
}

/**
 * Wait for transaction hash
 */
export async function waitForTransactionHash(transactionId) {
  if (!isValidTransactionId(transactionId)) {
    throw new Error("Invalid transaction ID format");
  }
  const client = getClient();
  const txHash = await Engine.waitForTransactionHash({
    client,
    transactionId: transactionId.trim(),
  });
  return txHash;
}

/**
 * CLI Handler for Python subprocess execution
 */
async function runCLI() {
  const args = process.argv.slice(2);
  const command = args[0];

  try {
    if (command === "claim1155") {
      const payload = JSON.parse(args[1] || "{}");
      const res = await claimERC1155(payload);
      console.log(JSON.stringify({ success: true, data: res }));
      process.exit(0);
    } else if (command === "status") {
      const txId = args[1];
      if (!txId || !isValidTransactionId(txId)) throw new Error("Valid transaction ID required");
      const res = await getTransactionStatus(txId);
      console.log(JSON.stringify({ success: true, data: res }));
      process.exit(0);
    } else if (command === "wait-hash") {
      const txId = args[1];
      if (!txId || !isValidTransactionId(txId)) throw new Error("Valid transaction ID required");
      const hash = await waitForTransactionHash(txId);
      console.log(JSON.stringify({ success: true, data: { transactionHash: hash } }));
      process.exit(0);
    } else if (command === "info") {
      console.log(
        JSON.stringify({
          success: true,
          data: {
            hasSecretKey: !!process.env.THIRDWEB_SECRET_KEY,
            hasClientId: !!process.env.THIRDWEB_CLIENT_ID,
            serverWallet: process.env.THIRDWEB_SERVER_WALLET_ADDRESS || null,
            engineUrl: process.env.THIRDWEB_ENGINE_URL || null,
            defaultChain: "base-sepolia",
          },
        })
      );
      process.exit(0);
    } else {
      console.log(
        JSON.stringify({
          success: false,
          error: `Unknown command: ${command}. Supported: claim1155, status, wait-hash, info`,
        })
      );
      process.exit(1);
    }
  } catch (err) {
    const rawMsg = err.message || String(err);
    // Sanitize any secret keys or internal private keys from error message
    let sanitizedMsg = rawMsg
      .replace(/THIRDWEB_SECRET_KEY=[^\s&]+/g, "THIRDWEB_SECRET_KEY=***")
      .replace(/THIRDWEB_SERVER_PRIVATE_KEY=[^\s&]+/g, "THIRDWEB_SERVER_PRIVATE_KEY=***");

    if (process.env.THIRDWEB_SECRET_KEY && process.env.THIRDWEB_SECRET_KEY.length >= 8) {
      sanitizedMsg = sanitizedMsg.replaceAll(process.env.THIRDWEB_SECRET_KEY, "***");
    }
    if (process.env.THIRDWEB_SERVER_PRIVATE_KEY && process.env.THIRDWEB_SERVER_PRIVATE_KEY.length >= 8) {
      sanitizedMsg = sanitizedMsg.replaceAll(process.env.THIRDWEB_SERVER_PRIVATE_KEY, "***");
    }

    console.log(
      JSON.stringify({
        success: false,
        error: sanitizedMsg,
      })
    );
    process.exit(1);
  }
}

if (process.argv[1] && process.argv[1].endsWith("thirdweb_engine.mjs")) {
  runCLI();
}
