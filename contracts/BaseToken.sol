// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

/// @title BaseToken: ERC-20 mínimo y auditable, base de todos los dineros del laboratorio.
/// @notice Implementa el estándar ERC-20 sin dependencias externas. Los contratos hijos
///         definen la política monetaria (quién crea dinero, cuánto y cuándo).
abstract contract BaseToken {
    string public name;
    string public symbol;
    uint8 public constant decimals = 18;

    uint256 internal _totalSupply;
    mapping(address => uint256) internal _balances;
    mapping(address => mapping(address => uint256)) public allowance;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);

    constructor(string memory name_, string memory symbol_) {
        name = name_;
        symbol = symbol_;
    }

    function totalSupply() public view virtual returns (uint256) {
        return _totalSupply;
    }

    function balanceOf(address account) public view virtual returns (uint256) {
        return _balances[account];
    }

    function transfer(address to, uint256 value) external returns (bool) {
        _transfer(msg.sender, to, value);
        return true;
    }

    function approve(address spender, uint256 value) external returns (bool) {
        allowance[msg.sender][spender] = value;
        emit Approval(msg.sender, spender, value);
        return true;
    }

    function transferFrom(address from, address to, uint256 value) external returns (bool) {
        uint256 allowed = allowance[from][msg.sender];
        if (allowed != type(uint256).max) {
            require(allowed >= value, "allowance insuficiente");
            allowance[from][msg.sender] = allowed - value;
        }
        _transfer(from, to, value);
        return true;
    }

    function _transfer(address from, address to, uint256 value) internal virtual {
        require(to != address(0), "destino nulo");
        require(_balances[from] >= value, "saldo insuficiente");
        unchecked {
            _balances[from] -= value;
        }
        _balances[to] += value;
        emit Transfer(from, to, value);
    }

    function _mint(address to, uint256 value) internal virtual {
        require(to != address(0), "destino nulo");
        _totalSupply += value;
        _balances[to] += value;
        emit Transfer(address(0), to, value);
    }

    function _burn(address from, uint256 value) internal virtual {
        require(_balances[from] >= value, "saldo insuficiente");
        unchecked {
            _balances[from] -= value;
            _totalSupply -= value;
        }
        emit Transfer(from, address(0), value);
    }
}

/// @title FixedPoint: aritmética en punto fijo de 18 decimales.
library FixedPoint {
    uint256 internal constant ONE = 1e18;

    /// @notice base^exp con base en punto fijo (1e18 = 1), por exponenciación binaria.
    function powu(uint256 base, uint256 exp) internal pure returns (uint256 result) {
        result = ONE;
        while (exp > 0) {
            if (exp & 1 == 1) result = (result * base) / ONE;
            base = (base * base) / ONE;
            exp >>= 1;
        }
    }
}

/// @title Owned: un único responsable (banco central, Tesoro, registro civil...).
abstract contract Owned {
    address public owner;

    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);

    modifier onlyOwner() {
        require(msg.sender == owner, "solo el responsable");
        _;
    }

    constructor() {
        owner = msg.sender;
        emit OwnershipTransferred(address(0), msg.sender);
    }

    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "responsable nulo");
        emit OwnershipTransferred(owner, newOwner);
        owner = newOwner;
    }
}
