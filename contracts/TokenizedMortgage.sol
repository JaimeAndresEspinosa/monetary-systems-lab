// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import "./BaseToken.sol";

interface IERC20 {
    function transferFrom(address from, address to, uint256 value) external returns (bool);
    function transfer(address to, uint256 value) external returns (bool);
}

/// @title HouseRegistry: registro de la propiedad como NFT (ERC-721 mínimo).
contract HouseRegistry is Owned {
    string public constant name = "Lab Property Registry";
    string public constant symbol = "LHOUSE";

    mapping(uint256 => address) public ownerOf;
    mapping(uint256 => address) public getApproved;
    mapping(uint256 => string) public cadastralRef;
    mapping(address => uint256) public balanceOf;
    uint256 public nextId = 1;

    event Transfer(address indexed from, address indexed to, uint256 indexed tokenId);
    event Approval(address indexed owner, address indexed approved, uint256 indexed tokenId);

    /// @notice El registro (owner) inscribe una vivienda a nombre de su propietario.
    function register(address to, string calldata ref) external onlyOwner returns (uint256 id) {
        id = nextId++;
        ownerOf[id] = to;
        cadastralRef[id] = ref;
        balanceOf[to] += 1;
        emit Transfer(address(0), to, id);
    }

    function approve(address to, uint256 id) external {
        require(msg.sender == ownerOf[id], "no es el propietario");
        getApproved[id] = to;
        emit Approval(msg.sender, to, id);
    }

    function transferFrom(address from, address to, uint256 id) public {
        require(ownerOf[id] == from, "propietario incorrecto");
        require(msg.sender == from || msg.sender == getApproved[id], "no autorizado");
        require(to != address(0), "destino nulo");
        delete getApproved[id];
        ownerOf[id] = to;
        balanceOf[from] -= 1;
        balanceOf[to] += 1;
        emit Transfer(from, to, id);
    }
}

/// @title TokenizedMortgage: hipoteca como contrato inteligente.
/// @notice La vivienda (NFT) queda depositada en el contrato hasta que se paga el préstamo.
///   · Cuota de un préstamo francés calculada en el propio contrato.
///   · Si el prestatario paga todas las cuotas, el NFT pasa a ser suyo automáticamente.
///   · Si acumula `graceMonths` cuotas impagadas, el prestamista puede ejecutar la garantía.
///   Lo que el código NO puede hacer: desalojar físicamente a nadie. Para eso hace falta un
///   juez; el contrato solo cambia quién figura como propietario (el "problema del oráculo").
contract TokenizedMortgage {
    using FixedPoint for uint256;

    enum Status { Created, Active, Repaid, Foreclosed }

    IERC20 public immutable money;
    HouseRegistry public immutable registry;
    uint256 public immutable houseId;
    address public immutable lender;
    address public immutable borrower;
    uint256 public immutable principal;
    uint256 public immutable monthlyRate;      // 1e18
    uint256 public immutable months;
    uint256 public immutable installment;
    uint256 public immutable graceMonths;
    uint256 public constant MONTH = 30 days;

    uint256 public start;
    uint256 public balance;
    uint256 public paidInstallments;
    Status public status;

    event Funded(uint256 principal, uint256 installment);
    event Paid(uint256 indexed number, uint256 interest, uint256 principalPart, uint256 remaining);
    event Repaid();
    event Foreclosed(uint256 missed);

    constructor(
        address money_, address registry_, uint256 houseId_, address lender_, address borrower_,
        uint256 principal_, uint256 annualRateBps, uint256 months_, uint256 graceMonths_
    ) {
        money = IERC20(money_);
        registry = HouseRegistry(registry_);
        houseId = houseId_;
        lender = lender_;
        borrower = borrower_;
        principal = principal_;
        months = months_;
        graceMonths = graceMonths_;
        uint256 r = (annualRateBps * FixedPoint.ONE) / (10_000 * 12);
        monthlyRate = r;
        if (r == 0) {
            installment = principal_ / months_;
        } else {
            uint256 f = (FixedPoint.ONE + r).powu(months_);         // (1 + r)^n
            installment = (principal_ * r / FixedPoint.ONE) * f / (f - FixedPoint.ONE);
        }
    }

    /// @notice 1) El prestatario aprueba el NFT; 2) el prestamista aprueba el dinero y llama aquí.
    function fund() external {
        require(msg.sender == lender && status == Status.Created, "no permitido");
        registry.transferFrom(borrower, address(this), houseId);      // la casa queda en garantía
        require(money.transferFrom(lender, borrower, principal), "fallo al transferir");
        start = block.timestamp;
        balance = principal;
        status = Status.Active;
        emit Funded(principal, installment);
    }

    function dueInstallments() public view returns (uint256) {
        if (status != Status.Active) return 0;
        uint256 elapsed = (block.timestamp - start) / MONTH;
        return elapsed > months ? months : elapsed;
    }

    function missed() public view returns (uint256) {
        uint256 due = dueInstallments();
        return due > paidInstallments ? due - paidInstallments : 0;
    }

    function pay() external {
        require(status == Status.Active, "no activa");
        uint256 interest = (balance * monthlyRate) / FixedPoint.ONE;
        uint256 amount = installment;
        if (paidInstallments + 1 == months || amount > balance + interest) amount = balance + interest;
        uint256 principalPart = amount - interest;
        require(money.transferFrom(msg.sender, lender, amount), "fallo en el pago");
        balance -= principalPart;
        paidInstallments += 1;
        emit Paid(paidInstallments, interest, principalPart, balance);
        if (balance == 0) {
            status = Status.Repaid;
            registry.transferFrom(address(this), borrower, houseId);
            emit Repaid();
        }
    }

    function foreclose() external {
        require(msg.sender == lender && status == Status.Active, "no permitido");
        uint256 m = missed();
        require(m >= graceMonths, "no hay impago suficiente");
        status = Status.Foreclosed;
        registry.transferFrom(address(this), lender, houseId);
        emit Foreclosed(m);
    }
}

/// @title LabStable: dinero de prueba para los ejemplos de hipoteca.
contract LabStable is BaseToken, Owned {
    constructor() BaseToken("Lab Stable Euro", "LSEUR") {}

    function mint(address to, uint256 value) external onlyOwner {
        _mint(to, value);
    }
}
