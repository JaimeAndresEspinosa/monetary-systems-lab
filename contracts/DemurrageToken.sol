// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import "./BaseToken.sol";

/// @title DemurrageToken: "dinero que se oxida" (Silvio Gesell, Wörgl 1932).
/// @notice Los saldos por encima de una franja exenta pierden `ratePerPeriod` cada periodo.
///         Lo que se oxida no desaparece: pasa al Tesoro (como los sellos de Wörgl).
///         El cálculo es "perezoso": se liquida cuando la cuenta se mueve, así que no hace
///         falta recorrer todas las cuentas cada mes. La oferta total se conserva.
contract DemurrageToken is BaseToken, Owned {
    using FixedPoint for uint256;

    uint256 public immutable ratePerPeriod;   // en 1e18 (0,005e18 = 0,5 % al mes)
    uint256 public immutable periodLength;
    uint256 public immutable exemption;       // saldo que no se oxida
    address public immutable treasury;
    uint256 public immutable start;

    mapping(address => uint256) public lastSettled;  // número de periodo de la última liquidación

    event Demurrage(address indexed account, uint256 fee, uint256 periods);

    constructor(uint256 ratePerPeriod_, uint256 periodLength_, uint256 exemption_, address treasury_)
        BaseToken("Lab Demurrage Money", "LDM")
    {
        require(ratePerPeriod_ < 1e18, "tasa invalida");
        ratePerPeriod = ratePerPeriod_;
        periodLength = periodLength_;
        exemption = exemption_;
        treasury = treasury_;
        start = block.timestamp;
    }

    function period() public view returns (uint256) {
        return (block.timestamp - start) / periodLength;
    }

    /// @notice Comisión pendiente de una cuenta: (saldo − exento) · (1 − (1 − r)^n).
    function pendingFee(address account) public view returns (uint256) {
        if (account == treasury) return 0;
        uint256 bal = _balances[account];
        if (bal <= exemption) return 0;
        uint256 n = period() - lastSettled[account];
        if (n == 0) return 0;
        uint256 taxable = bal - exemption;
        uint256 kept = (taxable * (FixedPoint.ONE - ratePerPeriod).powu(n)) / FixedPoint.ONE;
        return taxable - kept;
    }

    /// @notice Saldo efectivo, ya descontada la oxidación pendiente.
    function balanceOf(address account) public view override returns (uint256) {
        if (account == treasury) {
            return _balances[account];
        }
        return _balances[account] - pendingFee(account);
    }

    function settle(address account) public {
        uint256 fee = pendingFee(account);
        uint256 n = period() - lastSettled[account];
        lastSettled[account] = period();
        if (fee > 0) {
            _balances[account] -= fee;
            _balances[treasury] += fee;
            emit Transfer(account, treasury, fee);
            emit Demurrage(account, fee, n);
        }
    }

    function _transfer(address from, address to, uint256 value) internal override {
        settle(from);
        settle(to);
        super._transfer(from, to, value);
    }

    /// @notice El Tesoro emite la oferta inicial (transición desde el dinero anterior).
    function mint(address to, uint256 value) external onlyOwner {
        settle(to);
        _mint(to, value);
    }
}
