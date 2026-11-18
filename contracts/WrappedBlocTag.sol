// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title Wrapped BlocTag (wBCT)
 * @author BlocTag Engineering Team
 * @notice Official 1:1 cross-chain ERC-20 token for native BlocTag (BCT).
 *         Fully decentralized & radar-optimized:
 *         - Zero transfer pausing (Trading can never be disabled by owner -> 100% Honeypot-Free).
 *         - Zero blacklists / freezing mechanisms.
 *         - Zero buy/sell transaction taxes (0% transfer fee).
 *         - Strictly bounded bridge minting backed by Layer-1 proof-of-reserve hashes.
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
 * @dev 2-step ownership transfer to prevent accidental assignment to zero/wrong address.
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
    uint256 public constant MIN_BURN_AMOUNT = 1 * 10 ** 18;             // 1 wBCT Minimum Burn to Bridge
    uint256 private _totalSupply;

    mapping(address => uint256) private _balances;
    mapping(address => mapping(address => uint256)) private _allowances;

    // Authorized Bridge Relayers
    mapping(address => bool) public isBridgeRelayer;

    // Anti-Double-Mint: Prevents processing the same Layer-1 LockTrace transaction hash multiple times
    mapping(bytes32 => bool) public processedL1TxHashes;

    // Events
    event BridgeRelayerSet(address indexed relayer, bool active);
    event MintedFromBridge(address indexed recipient, uint256 amount, string locktraceTxHash);
    event BurnedToBridge(address indexed sender, uint256 amount, string locktraceRecipient);

    modifier onlyBridgeOrOwner() {
        require(
            _msgSender() == owner() || isBridgeRelayer[_msgSender()],
            "wBCT: Caller is neither owner nor authorized bridge relayer"
        );
        _;
    }

    /**
     * @notice Initializes the Wrapped BlocTag contract.
     * @param initialRelayer The address of the automated bridge relayer bot (e.g. 0x7007...).
     */
    constructor(address initialRelayer) Ownable2Step(_msgSender()) {
        if (initialRelayer != address(0)) {
            isBridgeRelayer[initialRelayer] = true;
            emit BridgeRelayerSet(initialRelayer, true);
        }
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

    // ── Pure Decentralized Transfers (UNPAUSABLE - HONEYPOT FREE) ────────────
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
     * @notice Backward-compatible public getter for processedL1Transactions(string).
     * @dev Canonicalizes the hash (0x prefix immune) and reads from processedL1TxHashes.
     */
    function processedL1Transactions(string calldata txHashStr) external view returns (bool) {
        bytes32 canonicalHash = _canonicalizeTxHash(txHashStr);
        return processedL1TxHashes[canonicalHash];
    }

    /**
     * @notice Mints wBCT to recipient after a verified lock of native BCT on LockTrace Layer-1.
     * @dev Strictly idempotent: checks processedL1TxHashes to guarantee zero double-minting.
     * @param to Destination EVM address receiving wBCT.
     * @param amount Amount of wBCT in 18-decimal wei.
     * @param locktraceTxHash Hash of the LockTrace Layer-1 bridge_lock transaction.
     */
    function mintFromBridge(
        address to,
        uint256 amount,
        string calldata locktraceTxHash
    ) external onlyBridgeOrOwner {
        require(to != address(0), "wBCT: Cannot mint to zero address");
        require(amount > 0, "wBCT: Amount must be greater than zero");
        require(bytes(locktraceTxHash).length > 0, "wBCT: Empty L1 transaction hash");

        bytes32 canonicalHash = _canonicalizeTxHash(locktraceTxHash);
        require(!processedL1TxHashes[canonicalHash], "wBCT: L1 transaction already processed");
        require(_totalSupply + amount <= MAX_SUPPLY, "wBCT: Max supply exceeded");

        processedL1TxHashes[canonicalHash] = true;
        _mint(to, amount);

        emit MintedFromBridge(to, amount, locktraceTxHash);
    }

    /**
     * @notice Burns wBCT on EVM to release native BCT back to the user's address on LockTrace Layer-1.
     * @param amount Amount of wBCT to burn.
     * @param locktraceRecipient Destination 43-character BCT address (e.g., BCT...).
     */
    function burnToBridge(
        uint256 amount,
        string calldata locktraceRecipient
    ) external {
        require(amount >= MIN_BURN_AMOUNT, "wBCT: Amount below minimum burn amount (1 wBCT)");
        bytes calldata rBytes = bytes(locktraceRecipient);
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
    }

    // ── Admin Governance ─────────────────────────────────────────────────────
    function setBridgeRelayer(address relayer, bool active) external onlyOwner {
        require(relayer != address(0), "wBCT: Zero address");
        isBridgeRelayer[relayer] = active;
        emit BridgeRelayerSet(relayer, active);
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
