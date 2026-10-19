// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import "./BaseToken.sol";

/// @title HalvingToken: regla de emisión "oferta fija tipo Bitcoin" + canal "mineros".
/// @notice Cada periodo (p. ej. un mes) se emite una recompensa que se reparte entre los
///         validadores según su peso. La recompensa se divide por dos cada `halvingEpochs`
///         periodos y la emisión se detiene al alcanzar `maxSupply`.
///         Es la misma regla que el simulador aplica en el régimen `fixed_supply`.
contract HalvingToken is BaseToken, Owned {
    uint256 public immutable maxSupply;
    uint256 public immutable initialReward;   // emisión por periodo antes del primer halving
    uint256 public immutable halvingEpochs;   // periodos entre halvings
    uint256 public immutable epochLength;     // duración de un periodo en segundos
    uint256 public immutable genesis;

    uint256 public lastMintedEpoch;
    bool public started;

    address[] public validators;
    mapping(address => uint256) public weight;
    uint256 public totalWeight;

    event ValidatorSet(address indexed validator, uint256 weight);
    event EpochMinted(uint256 indexed epoch, uint256 reward);

    /// @param genesisSupply_ oferta inicial (la transición desde el dinero anterior), al owner
    constructor(uint256 maxSupply_, uint256 initialReward_, uint256 halvingEpochs_, uint256 epochLength_,
                uint256 genesisSupply_)
        BaseToken("Lab Fixed-Supply Coin", "LFSC")
    {
        require(halvingEpochs_ > 0 && epochLength_ > 0, "parametros invalidos");
        require(genesisSupply_ <= maxSupply_, "genesis supera el maximo");
        if (genesisSupply_ > 0) _mint(msg.sender, genesisSupply_);
        maxSupply = maxSupply_;
        initialReward = initialReward_;
        halvingEpochs = halvingEpochs_;
        epochLength = epochLength_;
        genesis = block.timestamp;
    }

    function setValidator(address validator, uint256 w) external onlyOwner {
        if (weight[validator] == 0 && w > 0) validators.push(validator);
        totalWeight = totalWeight - weight[validator] + w;
        weight[validator] = w;
        emit ValidatorSet(validator, w);
    }

    function currentEpoch() public view returns (uint256) {
        return (block.timestamp - genesis) / epochLength;
    }

    /// @notice Recompensa programada de un periodo: initialReward / 2^(epoch / halvingEpochs).
    function rewardAt(uint256 epoch) public view returns (uint256) {
        uint256 halvings = epoch / halvingEpochs;
        if (halvings >= 256) return 0;
        return initialReward >> halvings;
    }

    /// @notice Cualquiera puede ejecutar la emisión de los periodos ya transcurridos.
    ///         Nadie puede emitir más ni antes: la regla está en el código.
    function mintEpochs() external returns (uint256 minted) {
        require(totalWeight > 0, "sin validadores");
        uint256 target = currentEpoch();
        uint256 from = started ? lastMintedEpoch + 1 : 0;
        for (uint256 e = from; e <= target; e++) {
            uint256 reward = rewardAt(e);
            if (_totalSupply + reward > maxSupply) reward = maxSupply - _totalSupply;
            if (reward == 0) break;
            uint256 distributed;
            for (uint256 i = 0; i < validators.length; i++) {
                address v = validators[i];
                uint256 share = (reward * weight[v]) / totalWeight;
                if (share > 0) {
                    _mint(v, share);
                    distributed += share;
                }
            }
            minted += distributed;
            emit EpochMinted(e, distributed);
        }
        lastMintedEpoch = target;
        started = true;
    }

    /// @notice Inflación anual implícita en el periodo actual (en puntos básicos).
    function annualIssuanceBps() external view returns (uint256) {
        if (_totalSupply == 0) return 0;
        uint256 perYear = (365 days) / epochLength;
        return (rewardAt(currentEpoch()) * perYear * 10_000) / _totalSupply;
    }
}
