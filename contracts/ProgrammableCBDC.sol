// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import "./BaseToken.sol";

/// @title ProgrammableCBDC: euro digital con límite de tenencia y dinero programable.
/// @notice Reproduce el diseño que estudia el BCE y sus riesgos, para poder discutirlos
///         con código y no con eslóganes:
///   · Límite de tenencia (p. ej. 3.000 €): lo que lo supera se envía automáticamente a la
///     cuenta bancaria vinculada ("cascada inversa"), para que los bancos no pierdan todos
///     sus depósitos.
///   · Estímulos programables: dinero que caduca y solo se puede gastar en comercios
///     autorizados. Es lo que el simulador llama "dinero programable".
///   · Congelación de cuentas: la capacidad técnica que preocupa a los críticos de las CBDC.
///     Está aquí, con un evento público, precisamente para que se vea.
contract ProgrammableCBDC is BaseToken, Owned {
    uint256 public holdingLimit;
    mapping(address => address) public linkedBank;      // cuenta bancaria para el exceso
    mapping(address => bool) public isIntermediary;     // bancos y comercios sin límite
    mapping(address => bool) public isMerchant;         // dónde se puede gastar el estímulo
    mapping(address => bool) public frozen;

    struct Stimulus {
        uint256 amount;
        uint64 expiry;
    }
    mapping(address => Stimulus) public stimulus;
    uint256 public totalStimulus;

    event HoldingLimitChanged(uint256 limit);
    event Waterfall(address indexed holder, address indexed bank, uint256 amount);
    event StimulusIssued(address indexed to, uint256 amount, uint64 expiry);
    event StimulusExpired(address indexed holder, uint256 amount);
    event AccountFrozen(address indexed account, bool frozen, string reason);

    constructor(uint256 holdingLimit_) BaseToken("Lab Digital Euro", "LDEUR") {
        holdingLimit = holdingLimit_;
        isIntermediary[msg.sender] = true;
    }

    // ------------------------------------------------------------- administración
    function setHoldingLimit(uint256 limit) external onlyOwner {
        holdingLimit = limit;
        emit HoldingLimitChanged(limit);
    }

    function setIntermediary(address a, bool on) external onlyOwner {
        isIntermediary[a] = on;
    }

    function setMerchant(address a, bool on) external onlyOwner {
        isMerchant[a] = on;
        isIntermediary[a] = on;
    }

    function linkBank(address bank) external {
        require(isIntermediary[bank], "no es un banco autorizado");
        linkedBank[msg.sender] = bank;
    }

    function freeze(address account, bool on, string calldata reason) external onlyOwner {
        frozen[account] = on;
        emit AccountFrozen(account, on, reason);
    }

    /// @notice Emisión ordinaria (p. ej. un banco cambia reservas por euro digital).
    function issue(address to, uint256 value) external onlyOwner {
        _mint(to, value);
        _enforceLimit(to);
    }

    /// @notice Estímulo programable: caduca en `expiry` y solo vale en comercios autorizados.
    function issueStimulus(address[] calldata to, uint256 value, uint64 expiry) external onlyOwner {
        require(expiry > block.timestamp, "caducidad en el pasado");
        for (uint256 i = 0; i < to.length; i++) {
            Stimulus storage s = stimulus[to[i]];
            if (s.amount > 0 && s.expiry <= block.timestamp) _expire(to[i]);
            s.amount += value;
            s.expiry = expiry;
            totalStimulus += value;
            _mint(to[i], value);
            emit StimulusIssued(to[i], value, expiry);
        }
    }

    /// @notice Cualquiera puede hacer caducar un estímulo vencido: vuelve al banco central.
    function expire(address holder) external {
        require(stimulus[holder].amount > 0 && stimulus[holder].expiry <= block.timestamp, "nada que caducar");
        _expire(holder);
    }

    function spendableAnywhere(address holder) public view returns (uint256) {
        return _balances[holder] - stimulus[holder].amount;
    }

    // ------------------------------------------------------------------ reglas
    function _transfer(address from, address to, uint256 value) internal override {
        require(!frozen[from] && !frozen[to], "cuenta congelada");
        Stimulus storage s = stimulus[from];
        if (s.amount > 0) {
            if (s.expiry <= block.timestamp) {
                _expire(from);
            } else {
                uint256 free = _balances[from] - s.amount;
                if (value > free) {
                    // se usa primero el saldo libre; el resto sale del estímulo
                    require(isMerchant[to], "el estimulo solo vale en comercios autorizados");
                    uint256 fromStim = value - free;
                    s.amount -= fromStim;
                    totalStimulus -= fromStim;
                }
            }
        }
        super._transfer(from, to, value);
        _enforceLimit(to);
    }

    function _enforceLimit(address holder) internal {
        if (isIntermediary[holder]) return;
        // el límite se aplica al saldo libre: el estímulo programable no se desvía al banco
        uint256 free = _balances[holder] - stimulus[holder].amount;
        if (free <= holdingLimit) return;
        address bank = linkedBank[holder];
        require(bank != address(0), "supera el limite y no tiene banco vinculado");
        uint256 excess = free - holdingLimit;
        super._transfer(holder, bank, excess);
        emit Waterfall(holder, bank, excess);
    }

    function _expire(address holder) internal {
        uint256 amount = stimulus[holder].amount;
        stimulus[holder].amount = 0;
        totalStimulus -= amount;
        _burn(holder, amount);
        emit StimulusExpired(holder, amount);
    }
}
