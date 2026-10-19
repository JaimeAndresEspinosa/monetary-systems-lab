// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import "./BaseToken.sol";

/// @title AlgorithmicDividend: regla "algoritmo del 2 %" + canal "dividendo ciudadano".
/// @notice Cada periodo la oferta crece un porcentaje fijo (`annualRateBps`, p. ej. 320 =
///         2 % de inflación objetivo + 1,2 % de productividad) y el dinero nuevo se reparte a
///         partes iguales entre los ciudadanos registrados. Nadie decide cuánto ni a quién.
///         Patrón "pull": cada ciudadano reclama lo suyo, sin bucles sobre toda la población.
contract AlgorithmicDividend is BaseToken, Owned {
    uint256 public immutable annualRateBps;
    uint256 public immutable periodLength;
    uint256 public immutable periodsPerYear;
    uint256 public lastIssue;

    mapping(address => bool) public isCitizen;
    uint256 public citizens;

    // dividendo acumulado por ciudadano desde el inicio (contabilidad "pull")
    uint256 public cumulativePerCitizen;
    mapping(address => uint256) public claimedIndex;
    uint256 public pendingSupply;   // emitido pero aún no reclamado (cuenta en la oferta)

    event CitizenRegistered(address indexed citizen);
    event Issued(uint256 periods, uint256 amount, uint256 perCitizen);
    event Claimed(address indexed citizen, uint256 amount);

    /// @param genesisHolder recibe la oferta inicial (la transición desde el sistema anterior)
    constructor(uint256 annualRateBps_, uint256 periodLength_, address genesisHolder, uint256 initialSupply)
        BaseToken("Lab Citizen Money", "LCM")
    {
        require(annualRateBps_ <= 2_000, "tasa demasiado alta");
        annualRateBps = annualRateBps_;
        periodLength = periodLength_;
        periodsPerYear = (365 days) / periodLength_;
        lastIssue = block.timestamp;
        _mint(genesisHolder, initialSupply);
    }

    /// @notice El registro civil (owner) da de alta a cada ciudadano una sola vez.
    function registerCitizen(address citizen) external onlyOwner {
        require(!isCitizen[citizen], "ya registrado");
        _settle(citizen);
        isCitizen[citizen] = true;
        claimedIndex[citizen] = cumulativePerCitizen;  // no cobra dividendos anteriores al alta
        citizens += 1;
        emit CitizenRegistered(citizen);
    }

    function totalSupply() public view override returns (uint256) {
        return _totalSupply + pendingSupply;
    }

    /// @notice Cualquiera puede ejecutar la emisión de los periodos vencidos.
    function issue() external returns (uint256 amount) {
        require(citizens > 0, "sin ciudadanos");
        uint256 periods = (block.timestamp - lastIssue) / periodLength;
        require(periods > 0, "periodo no vencido");
        uint256 supply = totalSupply();
        for (uint256 i = 0; i < periods; i++) {
            uint256 add = (supply * annualRateBps) / (10_000 * periodsPerYear);
            amount += add;
            supply += add;
        }
        uint256 perCitizen = amount / citizens;
        cumulativePerCitizen += perCitizen;
        pendingSupply += perCitizen * citizens;
        lastIssue += periods * periodLength;
        emit Issued(periods, perCitizen * citizens, perCitizen);
    }

    function owed(address citizen) public view returns (uint256) {
        if (!isCitizen[citizen]) return 0;
        return cumulativePerCitizen - claimedIndex[citizen];
    }

    function claim() external returns (uint256 amount) {
        amount = _settle(msg.sender);
    }

    function _settle(address citizen) internal returns (uint256 amount) {
        amount = owed(citizen);
        if (amount > 0) {
            claimedIndex[citizen] = cumulativePerCitizen;
            pendingSupply -= amount;
            _mint(citizen, amount);
            emit Claimed(citizen, amount);
        }
    }
}
