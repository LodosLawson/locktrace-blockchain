// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title Wrapped BlocTag (wBCT)
 * @author BlocTag Engineering Team
 * @notice Official 1:1 cross-chain ERC-20 token for native BlocTag (BCT).
 *         Audit-Hardened, Limit-Free & Radar-Optimized Architecture:
 *         - Zero transfer pausing (ERC-20 transfer/transferFrom can NEVER be paused -> 100% Honeypot-Free).
 *         - Zero blacklists / account freezing mechanisms.
 *         - Zero buy/sell transaction taxes (0% transfer fee).
 *         - Zero artificial minting caps (100% 1:1 liquidity mobility for any verified Layer-1 lock amount).
 *         - Native Multi-Relayer Quorum Consensus (`requiredApprovals` M-of-N relayer attestation) to eliminate
 *           single-private-key compromise risk without restricting legitimate user or liquidity bridge volume.
 *         - Strict Separation of Duties: Governance Owner != Bridge Relayer (`onlyBridgeRelayer`).
 *         - Future-Proof Layer-1 Address Validation (`strictL1AddressCheck` configurable if L1 address format upgrades).
 */

interface IERC20 {
    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);

    function totalSupply() external view returns (uint256);
    function balanceOf(address account) external view returns (uint256);
    function transfer(address to, uint256 value) external returns (bool);
    function allowance(address owner, address spender) external view returns (uint256);
    function approve(address spender, uint256 value) external returns (bool);
    function transferFrom(address from, address to, uint256 value) external returns (bool);
}

interface IERC20Metadata is IERC20 {
    function name() external view returns (string memory);
    function symbol() external view returns (string memory);
    function decimals() external view returns (uint8);
}

abstract contract Context {
    function _msgSender() internal view virtual returns (address) {
        return msg.sender;
    }
}

/**
 * @dev 2-step ownership transfer (OpenZeppelin Ownable2Step pattern) to prevent accidental
 *      assignment to an inactive, wrong, or zero address. Recommended to be governed by a Multisig (e.g. Safe).
 */
abstract contract Ownable2Step is Context {
    address private _owner;
    address private _pendingOwner;

    event OwnershipTransferStarted(address indexed previousOwner, address indexed newOwner);
    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);

    constructor(address initialOwner) {
        require(initialOwner != address(0), "Ownable: zero address");
        _owner = initialOwner;
        emit OwnershipTransferred(address(0), initialOwner);
    }

    function owner() public view virtual returns (address) {
        return _owner;
    }

    function pendingOwner() public view virtual returns (address) {
        return _pendingOwner;
    }

    modifier onlyOwner() {
        require(owner() == _msgSender(), "Ownable: caller is not the owner");
        _;
    }

    function transferOwnership(address newOwner) public virtual onlyOwner {
        require(newOwner != address(0), "Ownable2Step: zero address");
        _pendingOwner = newOwner;
        emit OwnershipTransferStarted(owner(), newOwner);
    }

    function acceptOwnership() public virtual {
        require(_pendingOwner == _msgSender(), "Ownable2Step: caller is not pending owner");
        address oldOwner = _owner;
        _owner = _msgSender();
        delete _pendingOwner;
        emit OwnershipTransferred(oldOwner, _msgSender());
    }
}

contract WrappedBlocTag is Context, IERC20Metadata, Ownable2Step {
    // ── Token Metadata ───────────────────────────────────────────────────────
    string private constant _name = "Wrapped BlocTag";
    string private constant _symbol = "wBCT";
    uint8 private constant _decimals = 18;

    uint256 public constant MAX_SUPPLY = 1_000_000_000_000 * 10 ** 18; // 1 Trillion wBCT Maximum Hard Cap
    uint256 public constant MIN_BURN_AMOUNT = 1 * 10 ** 18;             // 1 wBCT Minimum Burn to Bridge (Anti-Dust)
    uint256 private _totalSupply;

    mapping(address => uint256) private _balances;
    mapping(address => mapping(address => uint256)) private _allowances;

    // ── Separation of Duties & Multi-Relayer Quorum Consensus ────────────────
    // Eliminates single-key compromise risk without imposing artificial volume limits.
    // When requiredApprovals == 1, a single authorized relayer executes the mint immediately.
    // When requiredApprovals > 1 (M-of-N mode), M distinct authorized relayers must attest to the
    // exact same (to, amount, canonicalL1TxHash) payload before tokens are minted.
    mapping(address => bool) public isBridgeRelayer;
    uint256 public activeRelayerCount;
    uint256 public requiredApprovals;

    // Tracks M-of-N relayer approvals per deterministic bridge payload hash:
    // payloadHash = keccak256(abi.encode(to, amount, canonicalL1TxHash))
    mapping(bytes32 => uint256) public payloadApprovalCount;
    mapping(bytes32 => mapping(address => bool)) public hasRelayerApproved;

    // ── Bridge-Only Emergency Circuit Breaker & Address Validation Mode ──────
    // NOTE: `bridgePaused` affects ONLY bridge mint/burn operations.
    // Standard ERC-20 `transfer` and `transferFrom` are NEVER pausable.
    bool public bridgePaused = false;
    bool public strictL1AddressCheck = true;

    // ── Anti-Double-Mint: Layer-1 Transaction Hash Deduplication ─────────────
    mapping(bytes32 => bool) public processedL1TxHashes;

    // ── Events ───────────────────────────────────────────────────────────────
    event BridgeRelayerSet(address indexed relayer, bool active, uint256 activeRelayerCount);
    event RequiredApprovalsUpdated(uint256 oldQuorum, uint256 newQuorum);
    event BridgeMintAttested(
        bytes32 indexed canonicalL1TxHash,
        address indexed relayer,
        address indexed recipient,
        uint256 amount,
        uint256 currentApprovals,
        uint256 requiredApprovals
    );
    event BridgePausedSet(bool paused);
    event StrictL1AddressCheckSet(bool strict);

    /**
     * @dev Note on indexing: `recipient` and `sender` are indexed for fast topic filtering.
     *      `locktraceTxHash` and `locktraceRecipient` are intentionally unindexed `string` fields
     *      because Solidity hashes `indexed string` parameters into irreversible keccak256 topics,
     *      which would prevent off-chain bridge relayers from decoding the raw L1 address/txHash.
     */
    event MintedFromBridge(address indexed recipient, uint256 amount, string locktraceTxHash);
    event BurnedToBridge(address indexed sender, uint256 amount, string locktraceRecipient);

    // ── Modifiers ────────────────────────────────────────────────────────────
    modifier onlyBridgeRelayer() {
        require(
            isBridgeRelayer[_msgSender()],
            "wBCT: Caller is not an authorized bridge relayer"
        );
        _;
    }

    modifier whenBridgeNotPaused() {
        require(!bridgePaused, "wBCT: Bridge operations are currently paused");
        _;
    }

    /**
     * @notice Initializes the Wrapped BlocTag contract.
     * @param initialRelayer The address of the initial automated bridge relayer bot.
     */
    constructor(address initialRelayer) Ownable2Step(_msgSender()) {
        require(initialRelayer != address(0), "wBCT: Initial relayer cannot be zero address");
        isBridgeRelayer[initialRelayer] = true;
        activeRelayerCount = 1;
        requiredApprovals = 1;
        emit BridgeRelayerSet(initialRelayer, true, 1);
        emit RequiredApprovalsUpdated(0, 1);
    }

    // ── ERC20 Metadata ───────────────────────────────────────────────────────
    function name() public pure override returns (string memory) {
        return _name;
    }

    function symbol() public pure override returns (string memory) {
        return _symbol;
    }

    function decimals() public pure override returns (uint8) {
        return _decimals;
    }

    function totalSupply() public view override returns (uint256) {
        return _totalSupply;
    }

    function balanceOf(address account) public view override returns (uint256) {
        return _balances[account];
    }

    // ── Pure Decentralized Transfers (UNPAUSABLE - 100% HONEYPOT FREE) ───────
    function transfer(address to, uint256 value) public override returns (bool) {
        _transfer(_msgSender(), to, value);
        return true;
    }

    function allowance(address ownerAccount, address spender) public view override returns (uint256) {
        return _allowances[ownerAccount][spender];
    }

    function approve(address spender, uint256 value) public override returns (bool) {
        _approve(_msgSender(), spender, value);
        return true;
    }

    function transferFrom(address from, address to, uint256 value) public override returns (bool) {
        _spendAllowance(from, _msgSender(), value);
        _transfer(from, to, value);
        return true;
    }

    // ── Bridge Operations (Lock & Mint / Burn & Unlock) ──────────────────────

    /**
     * @notice Non-reverting public getter for processedL1Transactions(string).
     * @dev Canonicalizes the hash (casing and 0x-prefix immune) and reads from processedL1TxHashes.
     *      Safely returns false if the input string is not a valid 64-byte hex string.
     */
    function processedL1Transactions(string calldata txHashStr) external view returns (bool) {
        bytes calldata b = bytes(txHashStr);
        uint256 start = 0;
        if (b.length == 66 && b[0] == '0' && (b[1] == 'x' || b[1] == 'X')) {
            start = 2;
        } else if (b.length != 64) {
            return false;
        }
        bytes memory canonical = new bytes(32);
        for (uint256 i = 0; i < 32; i++) {
            bytes1 hiC = b[start + i * 2];
            bytes1 loC = b[start + i * 2 + 1];
            if (!_isValidHexChar(hiC) || !_isValidHexChar(loC)) {
                return false;
            }
            uint8 hi = _fromHexChar(hiC);
            uint8 lo = _fromHexChar(loC);
            canonical[i] = bytes1((hi << 4) | lo);
        }
        return processedL1TxHashes[bytes32(canonical)];
    }

    /**
     * @notice Mints wBCT to recipient after a verified lock of native BCT on Layer-1.
     * @dev Supports M-of-N Multi-Relayer Quorum Consensus without artificial amount caps:
     *      - If `requiredApprovals == 1`, mints immediately in a single transaction.
     *      - If `requiredApprovals > 1`, records the caller relayer's attestation and mints
     *        automatically as soon as the M-th distinct authorized relayer attests the exact same payload.
     * @param to Destination EVM address receiving wBCT.
     * @param amount Amount of wBCT in 18-decimal wei (1 BCT = 10^18 wei).
     * @param locktraceTxHash Hash of the Layer-1 bridge_lock transaction.
     */
    function mintFromBridge(
        address to,
        uint256 amount,
        string calldata locktraceTxHash
    ) external onlyBridgeRelayer whenBridgeNotPaused {
        require(to != address(0), "wBCT: Cannot mint to zero address");
        require(to != address(this), "wBCT: Cannot mint to token contract");
        require(amount > 0, "wBCT: Amount must be greater than zero");
        require(bytes(locktraceTxHash).length > 0, "wBCT: Empty L1 transaction hash");

        bytes32 canonicalHash = _canonicalizeTxHash(locktraceTxHash);
        require(!processedL1TxHashes[canonicalHash], "wBCT: L1 transaction already processed");
        require(_totalSupply + amount <= MAX_SUPPLY, "wBCT: Max supply exceeded");

        bytes32 payloadHash = keccak256(abi.encode(to, amount, canonicalHash));
        require(!hasRelayerApproved[payloadHash][_msgSender()], "wBCT: Relayer already attested this L1 tx");

        hasRelayerApproved[payloadHash][_msgSender()] = true;
        uint256 approvals = payloadApprovalCount[payloadHash] + 1;
        payloadApprovalCount[payloadHash] = approvals;

        emit BridgeMintAttested(canonicalHash, _msgSender(), to, amount, approvals, requiredApprovals);

        if (approvals >= requiredApprovals) {
            processedL1TxHashes[canonicalHash] = true;
            _mint(to, amount);
            emit MintedFromBridge(to, amount, locktraceTxHash);
        }
    }

    /**
     * @notice Burns wBCT on EVM to release native BCT back to the user's address on Layer-1.
     * @param amount Amount of wBCT to burn (minimum 1 wBCT).
     * @param locktraceRecipient Destination Layer-1 address (default: 43-char BCT... format).
     */
    function burnToBridge(
        uint256 amount,
        string calldata locktraceRecipient
    ) external whenBridgeNotPaused {
        require(amount >= MIN_BURN_AMOUNT, "wBCT: Amount below minimum burn amount (1 wBCT)");
        bytes calldata rBytes = bytes(locktraceRecipient);

        if (strictL1AddressCheck) {
            require(rBytes.length == 43, "wBCT: Invalid LockTrace address length");
            require(
                rBytes[0] == 'B' &&
                rBytes[1] == 'C' &&
                rBytes[2] == 'T',
                "wBCT: Must start with BCT prefix"
            );

            bool hasNonZero = false;
            for (uint256 i = 3; i < 43; i++) {
                bytes1 b = rBytes[i];
                require(_isValidHexChar(b), "wBCT: Address must contain valid hex characters");
                if (b != '0') {
                    hasNonZero = true;
                }
            }
            require(hasNonZero, "wBCT: Cannot bridge to burn zero address");

            string memory canonicalRecipient = _toLowerL1Address(locktraceRecipient);
            _burn(_msgSender(), amount);
            emit BurnedToBridge(_msgSender(), amount, canonicalRecipient);
        } else {
            // Flexible validation mode if Layer-1 upgrades address format in a future protocol version
            require(rBytes.length >= 4 && rBytes.length <= 128, "wBCT: Invalid L1 recipient length");
            for (uint256 i = 0; i < rBytes.length; i++) {
                bytes1 b = rBytes[i];
                require(b >= 0x21 && b <= 0x7E, "wBCT: Recipient contains invalid ASCII characters");
            }
            _burn(_msgSender(), amount);
            emit BurnedToBridge(_msgSender(), amount, locktraceRecipient);
        }
    }

    // ── Admin Governance (Owner / Multisig Only) ─────────────────────────────

    /**
     * @notice Grants or revokes bridge relayer authorization while maintaining valid quorum bounds.
     */
    function setBridgeRelayer(address relayer, bool active) external onlyOwner {
        require(relayer != address(0), "wBCT: Zero address");
        bool currentlyActive = isBridgeRelayer[relayer];
        require(currentlyActive != active, "wBCT: Relayer already in requested state");

        isBridgeRelayer[relayer] = active;
        if (active) {
            activeRelayerCount += 1;
        } else {
            require(activeRelayerCount > requiredApprovals, "wBCT: Lower requiredApprovals before removing relayer");
            activeRelayerCount -= 1;
        }
        emit BridgeRelayerSet(relayer, active, activeRelayerCount);
    }

    /**
     * @notice Configures the M-of-N multi-relayer quorum required to execute a bridge mint.
     * @param newQuorum Number of distinct authorized relayers required (1 <= newQuorum <= activeRelayerCount).
     */
    function setRequiredApprovals(uint256 newQuorum) external onlyOwner {
        require(newQuorum >= 1 && newQuorum <= activeRelayerCount, "wBCT: Invalid quorum threshold");
        uint256 oldQuorum = requiredApprovals;
        requiredApprovals = newQuorum;
        emit RequiredApprovalsUpdated(oldQuorum, newQuorum);
    }

    /**
     * @notice Emergency circuit breaker for bridge mint/burn ONLY.
     *         Does NOT affect standard ERC-20 transfers or DEX trading.
     */
    function setBridgePaused(bool paused) external onlyOwner {
        bridgePaused = paused;
        emit BridgePausedSet(paused);
    }

    /**
     * @notice Toggles strict 43-char 'BCT' hex validation vs flexible ASCII validation
     *         to ensure future L1 address format upgrades never lock bridge burns.
     */
    function setStrictL1AddressCheck(bool strict) external onlyOwner {
        strictL1AddressCheck = strict;
        emit StrictL1AddressCheckSet(strict);
    }

    // ── Internal Helpers ─────────────────────────────────────────────────────
    function _transfer(address from, address to, uint256 value) internal {
        require(from != address(0), "wBCT: Transfer from zero address");
        require(to != address(0), "wBCT: Transfer to zero address");

        uint256 fromBalance = _balances[from];
        require(fromBalance >= value, "wBCT: Transfer amount exceeds balance");
        unchecked {
            _balances[from] = fromBalance - value;
            _balances[to] += value;
        }

        emit Transfer(from, to, value);
    }

    function _mint(address account, uint256 value) internal {
        _totalSupply += value;
        unchecked {
            _balances[account] += value;
        }
        emit Transfer(address(0), account, value);
    }

    function _burn(address account, uint256 value) internal {
        uint256 accountBalance = _balances[account];
        require(accountBalance >= value, "wBCT: Burn amount exceeds balance");
        unchecked {
            _balances[account] = accountBalance - value;
            _totalSupply -= value;
        }
        emit Transfer(account, address(0), value);
    }

    function _approve(address ownerAccount, address spender, uint256 value) internal {
        require(ownerAccount != address(0), "wBCT: Approve from zero address");
        require(spender != address(0), "wBCT: Approve to zero address");

        _allowances[ownerAccount][spender] = value;
        emit Approval(ownerAccount, spender, value);
    }

    function _spendAllowance(address ownerAccount, address spender, uint256 value) internal {
        uint256 currentAllowance = allowance(ownerAccount, spender);
        if (currentAllowance != type(uint256).max) {
            require(currentAllowance >= value, "wBCT: Insufficient allowance");
            unchecked {
                _approve(ownerAccount, spender, currentAllowance - value);
            }
        }
    }

    function _isValidHexChar(bytes1 b) private pure returns (bool) {
        return (b >= '0' && b <= '9') || (b >= 'a' && b <= 'f') || (b >= 'A' && b <= 'F');
    }

    function _fromHexChar(bytes1 c) private pure returns (uint8) {
        if (c >= '0' && c <= '9') return uint8(c) - uint8(bytes1('0'));
        if (c >= 'a' && c <= 'f') return 10 + uint8(c) - uint8(bytes1('a'));
        if (c >= 'A' && c <= 'F') return 10 + uint8(c) - uint8(bytes1('A'));
        revert("wBCT: Invalid hex char in L1 tx hash");
    }

    function _canonicalizeTxHash(string calldata txHashStr) internal pure returns (bytes32) {
        bytes calldata b = bytes(txHashStr);
        uint256 start = 0;
        if (b.length == 66 && b[0] == '0' && (b[1] == 'x' || b[1] == 'X')) {
            start = 2;
        } else {
            require(b.length == 64, "wBCT: L1 tx hash must be 64 hex chars");
        }
        bytes memory canonical = new bytes(32);
        for (uint256 i = 0; i < 32; i++) {
            uint8 hi = _fromHexChar(b[start + i * 2]);
            uint8 lo = _fromHexChar(b[start + i * 2 + 1]);
            canonical[i] = bytes1((hi << 4) | lo);
        }
        return bytes32(canonical);
    }

    function _toLowerL1Address(string calldata addr) internal pure returns (string memory) {
        bytes calldata b = bytes(addr);
        bytes memory lower = new bytes(43);
        lower[0] = 'B';
        lower[1] = 'C';
        lower[2] = 'T';
        for (uint256 i = 3; i < 43; i++) {
            bytes1 c = b[i];
            if (c >= 'A' && c <= 'F') {
                lower[i] = bytes1(uint8(c) + 32);
            } else {
                lower[i] = c;
            }
        }
        return string(lower);
    }
}
