// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title Wrapped Blockchain Trace (wBCT)
 * @author LockTrace Decentralized Engineering Team
 * @notice Official 1:1 cross-chain ERC-20 representation of native LockTrace (BCT).
 *         Enables decentralized trading on Uniswap, PancakeSwap, and EVM lending protocols.
 *         Deployed on Base Mainnet, Arbitrum One, and Ethereum.
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

abstract contract Ownable is Context {
    address private _owner;

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
        require(newOwner != address(0), "Ownable: zero address");
        emit OwnershipTransferred(_owner, newOwner);
        _owner = newOwner;
    }
}

abstract contract Pausable is Context {
    bool private _paused;

    event Paused(address account);
    event Unpaused(address account);

    constructor() {
        _paused = false;
    }

    function paused() public view virtual returns (bool) {
        return _paused;
    }

    modifier whenNotPaused() {
        require(!paused(), "Pausable: paused");
        _;
    }

    modifier whenPaused() {
        require(paused(), "Pausable: not paused");
        _;
    }

    function _pause() internal virtual whenNotPaused {
        _paused = true;
        emit Paused(_msgSender());
    }

    function _unpause() internal virtual whenPaused {
        _paused = false;
        emit Unpaused(_msgSender());
    }
}

contract WrappedBCT is Context, IERC20Metadata, Ownable, Pausable {
    string private constant _name = "Wrapped Blockchain Trace";
    string private constant _symbol = "wBCT";
    uint8 private constant _decimals = 18;

    uint256 public constant MAX_SUPPLY = 1_000_000_000_000 * 10 ** 18; // 1 Trillion wBCT
    uint256 private _totalSupply;

    mapping(address => uint256) private _balances;
    mapping(address => mapping(address => uint256)) private _allowances;

    // Authorized Bridge Relayers
    mapping(address => bool) public isBridgeRelayer;

    // Deduplication mapping: Prevents double-minting of Layer-1 LockTrace transaction hashes
    mapping(string => bool) public processedL1Transactions;
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

    constructor(address initialRelayer) Ownable(_msgSender()) {
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

    // ── Standard ERC20 Transfers ─────────────────────────────────────────────
    function transfer(address to, uint256 value) public override whenNotPaused returns (bool) {
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

    function transferFrom(address from, address to, uint256 value) public override whenNotPaused returns (bool) {
        _spendAllowance(from, _msgSender(), value);
        _transfer(from, to, value);
        return true;
    }

    // ── Bridge Operations (Lock & Mint / Burn & Unlock) ──────────────────────
    
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

    /**
     * @notice Mints wBCT to recipient after a verified lock of native BCT on LockTrace Layer-1.
     * @dev Strictly idempotent: checks processedL1Transactions and processedL1TxHashes to guarantee zero double-minting.
     * @param to Destination EVM address receiving wBCT.
     * @param amount Amount of wBCT in 18-decimal wei (1 BCT = 10^18 wei).
     * @param locktraceTxHash Hash of the LockTrace Layer-1 bridge_lock transaction.
     */
    function mintFromBridge(
        address to,
        uint256 amount,
        string calldata locktraceTxHash
    ) external onlyBridgeOrOwner whenNotPaused {
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

    function _isValidHexChar(bytes1 b) private pure returns (bool) {
        return (b >= '0' && b <= '9') || (b >= 'a' && b <= 'f') || (b >= 'A' && b <= 'F');
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

    /**
     * @notice Burns wBCT on EVM to release native BCT back to the user's address on LockTrace Layer-1.
     * @dev Address format: "BCT" prefix + 40 hexadecimal characters (case-insensitive, canonicalized to lowercase on L1).
     * @param amount Amount of wBCT to burn.
     * @param locktraceRecipient Destination 43-character BCT address (e.g., BCT...).
     */
    function burnToBridge(
        uint256 amount,
        string calldata locktraceRecipient
    ) external whenNotPaused {
        require(amount > 0, "wBCT: Amount must be greater than zero");
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

    // ── Admin & Governance ───────────────────────────────────────────────────
    function setBridgeRelayer(address relayer, bool active) external onlyOwner {
        require(relayer != address(0), "wBCT: Zero address");
        isBridgeRelayer[relayer] = active;
        emit BridgeRelayerSet(relayer, active);
    }

    function pause() external onlyOwner {
        _pause();
    }

    function unpause() external onlyOwner {
        _unpause();
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
}
