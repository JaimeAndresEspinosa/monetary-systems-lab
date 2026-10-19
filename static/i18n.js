// Traducción al inglés. El español es el idioma base (está en el HTML y en la API);
// aquí solo está lo que cambia en inglés.

export const lang = () => (document.documentElement.lang === "en" ? "en" : "es");
export const T = (es, en) => (lang() === "en" ? en : es);
export const LOCALE = () => (lang() === "en" ? "en-GB" : "es-ES");

export const UI = {
  "brand.sub": "Monetary systems simulator",
  "nav.lab": "Lab", "nav.compare": "Compare", "nav.explore": "Explorer", "nav.sens": "Sensitivity",
  "nav.data": "Real data", "nav.chain": "Blockchain", "nav.method": "Methodology",
  "pill.sfc": "Accounting",
  "lab.title": "Design the rules of money and see what happens to the economy",
  "lab.lead": "A virtual country of thousands of households, firms, banks, a government and a central bank, with complete double-entry accounting and calibrated to Spanish data. Pick one piece from each column: there are 576 different monetary systems.",
  "ctl.preset": "Known systems", "ctl.shock": "Crisis", "ctl.shockyear": "Hits in", "ctl.horizon": "Horizon",
  "ctl.households": "Households", "ctl.seeds": "Runs", "ctl.scenario": "Scenario", "ctl.variable": "Variable",
  "ctl.system": "System", "ctl.result": "Outcome",
  "btn.run": "Simulate", "btn.compare": "Compare", "btn.more": "Show all",
  "adv.summary": "Economy parameters",
  "adv.note": "Defaults are the calibration to Spanish data (see Real data). Changing them is a sensitivity analysis.",
  "lab.evo": "Paths", "lab.evo.sub": "Line: median across runs. Band: 10th to 90th percentile, the range of outcomes due to chance.",
  "lab.who": "Who wins and who loses?",
  "lab.who.sub": "Change in each decile's share of total wealth (the same households, ranked by initial wealth). This is where the Cantillon effect shows up: whoever gets the new money first, or owns the assets that rise, gains share.",
  "lab.dec.title": "Change in wealth share by decile", "lab.dec.sub": "D1 = poorest 10 % at the start · D10 = richest 10 %",
  "lg.gain": "Gains share", "lg.lose": "Loses share",
  "lab.nm.title": "Where does new money enter?", "lab.nm.sub": "First recipient of the base money created during the run",
  "lab.nm.dec": "Households receiving it directly, by wealth decile",
  "lab.acct": "Accounting",
  "lab.acct.sub": "Balance sheets of every sector in the last month (first run). Every financial row sums to zero: one sector's asset is another's liability. Total net worth equals real assets.",
  "acct.bs": "Balance sheets", "acct.flows": "Monthly flows", "lab.events": "Events",
  "lab.empty": "Pick a system and press <b>Simulate</b>.",
  "cmp.title": "Up to three systems, side by side",
  "cmp.lead": "Same starting economy, same random seeds and the same crisis: the only difference is the rules of money.",
  "cmp.paths": "Paths", "cmp.paths.sub": "Choose the variable.", "cmp.summary": "Summary",
  "cmp.summary.sub": "Median across runs; 10–90 % range in brackets. Green: best of the three.",
  "exp.title": "Every combination, none left out",
  "exp.effects": "Effect of each building block",
  "exp.effects.sub": "How much each option moves the chosen variable relative to the average across all combinations (main effect). It separates which part of the outcome comes from each dimension of the monetary system.",
  "exp.table": "The combinations", "exp.table.sub": "Colour: better or worse than today's system on that variable. Click a row to open it in the lab.",
  "sens.title": "Which assumptions really drive the results?",
  "sens.lead": "Global sensitivity analysis with Sobol indices: eight uncertain parameters vary together within plausible ranges and the variance of each outcome is decomposed. If a conclusion hinges on a debatable assumption, it shows here.",
  "sens.chart.sub": "Share of the non-random variance each assumption is involved in, including interactions", "sens.read": "How to read it",
  "sens.noise": "Simulation randomness", "sens.st": "ST: total effect of the assumption",
  "data.title": "Calibrated and validated with Spanish data",
  "data.lead": "Today's system is calibrated by the simulated method of moments (SMM) to reproduce Eurostat data and the ECB Distributional Wealth Accounts. Here is the full comparison, including what the model does not yet reproduce well.",
  "data.moments": "Moments: Spain vs the model", "data.stylized": "Stylised facts",
  "data.stylized.sub": "Relationships the model does not impose and should reproduce on its own",
  "data.params": "Calibrated parameters", "data.series": "Spain's series",
  "chain.title": "The rules of money, written as smart contracts",
  "chain.lead": "Every rule in the simulator is implemented in Solidity and tested on an Ethereum chain. The fixed-supply rule is calibrated to real Bitcoin data, and stablecoins show which private digital money already exists.",
  "chain.btc": "Bitcoin: supply according to the protocol", "chain.stables": "Stablecoins in circulation",
  "chain.same": "The contract and the model agree",
  "chain.same.sub": "The same rule run for 10 years in the simulator and as a contract on a local Ethereum chain. If the lines overlap, the model describes something that can really be programmed.",
  "chain.halving": "Fixed supply with halvings", "chain.dividend": "Algorithm + citizen dividend",
  "chain.demurrage": "Demurrage money: an idle balance of 10,000", "chain.cbdc": "Digital euro: what the contract does",
  "chain.mortgage": "Tokenised mortgage: first year", "chain.gas": "Cost of each operation (gas)",
  "chain.gas.sub": "EVM computation units. On a layer-2 network the cost in euros is a few cents.",
  "chain.code": "The code",
  "footer": "Monetary Systems Lab · an educational and research model. Results are simulations with explicit assumptions, not forecasts or financial advice.",
};

// Catálogo: dimensiones, opciones y crisis
export const CAT = {
  issuance: { label: "Issuance rule", help: "Who decides how much new base money is created, and on what basis.", options: {
    discretionary: ["Discretionary (today)", "Discretionary", "The central bank sets the interest rate with a Taylor rule and buys assets (QE) when inflation falls below target or unemployment spikes. Closest to today's ECB."],
    rule_2pct: ["2 % algorithm", "2 % algorithm", "Base money grows automatically at 2 % plus trend productivity growth. No human decisions."],
    gold: ["Gold standard", "Gold", "Base money is only created when gold reserves grow (≈1.5 % a year with noise). No lender of last resort."],
    fixed_supply: ["Bitcoin-style fixed supply", "Fixed supply", "Programmed issuance that halves every 4 years, calibrated to Bitcoin's current inflation (≈0.8 % a year). No lender of last resort."],
  } },
  channel: { label: "Channel of new money", help: "Where newly created base money enters the economy.", options: {
    banks: ["Banks (bond purchases)", "Banks", "The central bank buys bonds from banks and, when they run out, from the households holding them. Money enters through the financial system."],
    government: ["Public spending", "Government", "New money is credited to the Treasury, which spends it on goods and services. It reaches firms and their workers first."],
    dividend: ["Citizen dividend", "Dividend", "New money is shared equally among all households."],
    miners: ["Miners / validators", "Miners", "As in Bitcoin: new money goes to whoever owns the validation infrastructure (concentrated among the richest households)."],
  } },
  banking: { label: "Banking system", help: "Whether banks can create money when they lend, or only lend existing savings.", options: {
    fractional: ["Fractional reserve", "Fractional", "Banks create new deposits when they lend, limited by capital (8 %), reserve requirements (1 %) and borrower solvency."],
    full_reserve: ["100 % reserve", "Full reserve", "Chicago Plan: every deposit is backed by reserves. Banks only lend what savers place in investment accounts."],
  } },
  money: { label: "Properties of money", help: "What you can do with money once issued: hold it at no cost, or not.", options: {
    normal: ["Normal money", "Normal", "As today: holding money costs nothing (except inflation)."],
    demurrage: ["Demurrage money (Gesell)", "Demurrage", "Idle balances lose 0.5 % a month (≈6 % a year), which the State spends on public works the same month. It pushes savings into spending or investment. Inspired by Silvio Gesell and the Wörgl experiment (1932)."],
    cbdc: ["Programmable digital euro (CBDC)", "CBDC", "Households can hold money directly at the central bank, up to €3,000 (as the ECB proposes). New money received by households is programmable: it expires if not spent. Banks lose part of their deposits."],
  } },
  privacy: { label: "Privacy of money", help: "How much of each payment the tax authority can see. It affects evasion of capital income.", options: {
    mixed: ["Mixed (today)", "Mixed", "Bank accounts are visible, cash and opaque structures are not. ≈10 % of the capital income of the richest 20 % is evaded."],
    anonymous: ["Anonymous", "Anonymous", "Unidentified payments, like cash or a crypto without KYC. ≈25 % of the capital income of the richest 20 % is evaded."],
    traceable: ["Fully traceable", "Traceable", "Every payment is recorded. Evasion falls to ≈2 %. The cost, surveillance, is not measured in euros and the model does not quantify it."],
  } },
  fiscal: { label: "Fiscal rule", help: "Whether the State can borrow or must balance its books every year.", options: {
    free: ["Free deficit (today)", "Free deficit", "Public spending follows its trend and the deficit is financed with bonds."],
    balanced: ["Balanced budget", "Balanced", "Spending on goods and services adjusts to revenue (12-month average) minus pensions, benefits and interest. Benefits are still paid."],
  } },
};

export const SHOCKS_EN = {
  none: ["No crisis", "The economy evolves without external disturbances."],
  pandemic: ["Pandemic", "For 6 months consumption falls 25 % (lockdown) and investment 30 %."],
  banking: ["Banking crisis", "House prices fall 25 % at once, 6 % of business loans default, banks cut credit for 2 years and firms deleverage; for a year confidence falls (investment −30 %, consumption −6 %)."],
  energy: ["Energy shock", "Production costs jump (mark-up +10 points) and normalise within a year: imported inflation."],
  automation: ["Automation boom", "Productivity rises 10 % in a year: the same is produced with fewer workers."],
};

export const METRICS_EN = {
  inflation: "Annual inflation", price_level: "Price level", unemployment: "Unemployment", real_wage: "Real wage",
  real_gdp: "Real GDP", gini_wealth: "Wealth Gini", gini_income: "Income Gini", top10_wealth: "Wealth of the richest 10 %",
  bottom50_wealth: "Wealth of the poorest 50 %", house_price_real: "Real house price", price_to_income: "Years of salary per home",
  homeownership: "Home-owning households", rent_burden: "Rent / median wage", broad_money: "Total money / initial GDP",
  base_money: "Base money / initial GDP", new_money: "Base money issuance (annual, % GDP)", credit_gdp: "Credit / GDP",
  debt_gdp: "Public debt / GDP", policy_rate: "Policy rate", mortgage_rate: "Mortgage rate", foreclosures: "Foreclosures (cum.)",
  bank_capital: "Bank capital / loans", stock_index: "Stock market (real value of firms)", bailouts: "Bank bailouts (cum., % GDP)",
  cbdc_share: "Money held in digital euro", tax_gap: "Evaded taxes (% GDP)", demurrage: "Demurrage revenue (% GDP)",
};

export const SECTORS_EN = { hh: "Households", firm: "Firms", bank: "Banks", gov: "Government", cb: "Central bank" };
export const INSTRUMENTS_EN = {
  deposits: "Deposits", investment: "Investment accounts", loans: "Loans", reserves: "Reserves", treasury: "Treasury account",
  bonds: "Government bonds", cb_loans: "Central bank loans", cbdc: "Digital euro (CBDC)", houses: "Homes (real asset)", net: "Net worth",
};
export const FLOWS_EN = {
  "Salarios": "Wages", "Pensiones": "Pensions", "Prestaciones por desempleo": "Unemployment benefits",
  "Intereses de la deuda": "Interest on public debt", "Intereses de depósitos": "Deposit interest", "Dividendos": "Dividends",
  "Intereses de hipotecas": "Mortgage interest", "Amortización de préstamos": "Loan repayments", "Intereses de préstamos": "Loan interest",
  "Alquileres": "Rents", "IRPF y cotizaciones": "Income tax and social contributions", "Consumo": "Consumption",
  "Compras públicas": "Public purchases", "IVA": "VAT", "Impuesto de sociedades": "Corporate tax", "Nuevos préstamos": "New loans",
  "Compra de bonos nuevos": "New bond purchases", "Compra de bonos (QE)": "Bond purchases (QE)", "Préstamo de liquidez": "Liquidity loan",
  "Devolución de liquidez": "Liquidity repayment", "Compraventa de vivienda": "Home sales", "Compra de vivienda nueva": "New home purchases",
  "Compra de vivienda embargada": "Repossessed home purchases", "Paso a cuentas de inversión": "Transfers to investment accounts",
  "Retirada de cuentas de inversión": "Withdrawals from investment accounts", "Rescate bancario": "Bank bailout", "Dinero nuevo": "New money",
  "Oxidación del dinero": "Demurrage", "Paso a euro digital": "Moves into digital euro", "Vuelta a depósitos": "Moves back to deposits",
  "Dinero nuevo (euro digital)": "New money (digital euro)", "Caducidad del dinero programable": "Expiry of programmable money",
  "Compra de bonos a los bancos": "Bond purchases from banks",
};

export function applyStatic() {
  const en = lang() === "en";
  document.querySelectorAll("[data-i18n]").forEach((n) => {
    if (!n.dataset.es) n.dataset.es = n.textContent;
    n.textContent = en ? UI[n.dataset.i18n] || n.dataset.es : n.dataset.es;
  });
  document.querySelectorAll("[data-i18n-html]").forEach((n) => {
    if (!n.dataset.es) n.dataset.es = n.innerHTML;
    n.innerHTML = en ? UI[n.dataset.i18nHtml] || n.dataset.es : n.dataset.es;
  });
  document.getElementById("lang-btn").textContent = en ? "ES" : "EN";
}
