"""Seed 15-20 startups by running each through the REAL agent pipeline.
Each gets a genuine VC-structured card + verifier badges + trace log.
Run with: .venv/bin/python seed.py   (writes to data/)"""
import os, sys
import store, agents

store.init(os.path.join(os.path.dirname(__file__), "data"))

# (name, founder, linkedin, website, subthemes, problem, opp, whynow, stage,
#  proof, adopters, gtm, success, edge, looking_for)
SEED = [
    ("Recyclaro", "Neeti Patel", "https://linkedin.com/in/neetipatel", "https://recyclaro.com",
     ["waste-to-value", "circular-economy"],
     "Small Indian cities have no economic path to recycle plastic waste.",
     "12M tonnes/yr of plastic waste in India; ~$40B addressable recovery market.",
     "EPR rules now mandate producer takeback, creating guaranteed feedstock.",
     "pilot", "2 municipal pilots in Pune processing 3t/day.", "Municipal bodies / ULBs",
     "Equipment-as-a-service to urban local bodies.", "If EPR enforcement tightens, demand becomes mandatory.",
     "Deep municipal relationships and local logistics know-how.", "pilot partners"),

    ("Ticent Energy", "Arjun Rao", "https://linkedin.com/in/arjunrao", "https://ticent.energy",
     ["industrial-decarbonization", "waste-to-value"],
     "Cement kilns vent waste heat that could decarbonize nearby industry.",
     "India adds 100Mt cement/yr; recoverable waste-heat value ~$2B/yr.",
     "Carbon border taxes make embedded emissions costly for exporters.",
     "prototype", "Lab demo at 30kW thermal recovery.", "Cement majors",
     "Heat-recovery systems sold on performance contracts.", "If CBAM bites, payback drops below 2 years.",
     "Thermodynamics PhDs ex-IIT with kiln OEM ties.", "seed funding"),

    ("Mistify AI", "Kavya Singh", "https://linkedin.com/in/kavyasingh", "https://mistify.ai",
     ["climate-ai", "agritech-climate"],
     "Farmers cannot see micro-climate risk until crops have already failed.",
     "250M Indian farmers; ~$6B climate-advisory TAM.",
     "Cheap IoT sensors and better models make per-field forecasting viable.",
     "pilot", "3,000-farm pilot in Maharashtra showing 8% yield lift.", "Farmer producer orgs",
     "B2B2C via cooperatives and input retailers.", "If yields rise 8%, retention compounds annually.",
     "Agronomy + ML team from IIT Kharagpur.", "pilot partners"),

    ("Datoms", "Rohan Mehta", "https://linkedin.com/in/rohanmehta", "https://datoms.io",
     ["industrial-decarbonization", "grid-tech"],
     "Factory operators cannot see where energy is wasted in real time.",
     "Indian industrial energy spend ~$120B/yr; 10-15% is recoverable.",
     "Rising grid tariffs force manufacturers to manage demand actively.",
     "early revenue", "12 factories live, $180k ARR.", "Mid-size manufacturers",
     "SaaS + edge sensors, monthly subscription.", "If energy prices keep rising, ROI is immediate.",
     "Ex-Schneider energy engineers.", "funding"),

    ("MediGence", "Dr. Anita Bose", "https://linkedin.com/in/anitabose", "https://medigence.health",
     ["robotics-in-healthcare", "deep-tech-other"],
     "Rural India lacks specialist diagnostics within reachable distance.",
     "600k villages, ~1 doctor per 1,500 people in rural belts.",
     "Telemedicine rails are now mature enough to extend with robotics.",
     "prototype", "Robotic sample-handling kiosk validated in 2 PHCs.", "State health missions",
     "OEM + outcomes-based deployment with governments.", "If reimbursement clears, rollout is statewide.",
     "Roboticist + public-health physician co-founders.", "seed funding"),

    ("HydroLeaf", "Sandeep Nair", "https://linkedin.com/in/sandeepnair", "https://hydroleaf.in",
     ["water-tech", "agritech-climate"],
     "Flood-irrigated farms waste 40% of freshwater in key basins.",
     "India uses 80% of freshwater for agriculture; 40% is wasted.",
     "Groundwater depletion laws now restrict free extraction.",
     "pilot", "180-acre pilot cutting water use 35%.", "Cooperative farms",
     "Micro-drip sold via FPO bulk deals.", "If water entitlements tighten, adoption is forced.",
     "Irrigation engineers with Mandi distribution.", "pilot partners"),

    ("CarbonCraft", "Meera Iyer", "https://linkedin.com/in/meeraiyer", "https://carboncraft.tech",
     ["carbon-capture", "materials-science"],
     "CO2 from biogas plants is vented instead of being fixed into product.",
     "15k biogas plants; each flares ~1kt CO2/yr.",
     "Voluntary carbon prices recovered enough to fund capture.",
     "prototype", "Bench unit mineralizing 50kg CO2/day into aggregate.", "Biogas operators",
     "Capture modules leased per plant.", "If carbon prices hold, unit economics close.",
     "Materials scientists ex-IISc.", "seed funding"),

    ("GridWeave", "Vikram Reddy", "https://linkedin.com/in/vikramreddy", "https://gridweave.energy",
     ["grid-tech", "energy-storage"],
     "Rooftop solar owners cannot trade surplus without a coordination layer.",
     "India targets 300GW rooftop; peer trading market ~$3B.",
     "Net-metering reforms enable localized trading.",
     "idea", "Simulation validated against DISCOM data.", "Resident welfare assns",
     "Marketplace with smart-meter APIs.", "If regulations permit P2P, demand is instant.",
     "Ex-grid-operator + fintech builder.", "co-founder"),

    ("AeroSense", "Priya Nanda", "https://linkedin.com/in/priyananda", "https://aerosense.ai",
     ["climate-ai", "space-tech"],
     "Crop insurers price risk blind because field data is stale.",
     "Indian crop insurance ~$6B premium pool, largely manual.",
     "Satellite revisit + ML now gives weekly field truth.",
     "pilot", "Pilots with 2 insurers on 50k acres.", "Insurers / reinsurers",
     "API per-acre risk score, billed per policy.", "If loss ratios improve, renewals are locked.",
     "Remote-sensing PhDs + actuary advisor.", "funding"),

    ("BioBind", "Karthik S.", "https://linkedin.com/in/karthiks", "https://biobind.bio",
     ["materials-science", "waste-to-value"],
     "Mine tailings and red mud are stored as dead liability.",
     "200Mt/yr of red mud globally; India holds ~60Mt.",
     "Circular-material mandates push builders to seek substitutes.",
     "prototype", "Bricks from 70% red mud pass load tests.", "Cement / brick makers",
     "Licensed formulations to plants.", "If green-building codes spread, offtake is large.",
     "Ceramics researchers ex-NCL.", "seed funding"),

    ("VoltRural", "Sana Khan", "https://linkedin.com/in/sanakhan", "https://voltrural.in",
     ["energy-storage", "sustainable-mobility"],
     "Rural micro-enterprises have no affordable backup when grids fail.",
     "Rural power cuts cost SMEs ~$1.5B/yr in downtime.",
     "Lithium cell prices fell 80% in a decade.",
     "early revenue", "400 units sold, $90k revenue.", "Rural SMEs",
     "Direct + dealer network.", "If reliability matters more than capex, swap accelerates.",
     "Power-electronics team ex-Bajaj.", "funding"),

    ("SkyHarvest", "Aditya Joshi", "https://linkedin.com/in/adityajoshi", "https://skyharvest.agri",
     ["agritech-climate", "robotics-in-healthcare"],
     "Standing crops are damaged by disease detected too late by scouting.",
     "India loses ~$10B/yr to crop disease.",
     "Cheap drones + vision models enable weekly scouting.",
     "pilot", "Sprayed 1,200 acres, cut fungicide 30%.", "Contract farmers",
     "Per-acre scouting subscription.", "If input savings beat fee, adoption is automatic.",
     "Agri-engineers + CV researchers.", "pilot partners"),

    ("ThermaBridge", "Leela Menon", "https://linkedin.com/in/leelamenon", "https://thermabridge.tech",
     ["industrial-decarbonization", "materials-science"],
     "Data centers reject heat that nearby buildings could use.",
     "India data-center load ~1GW, growing 25%/yr; heat is free fuel.",
     "District-heating pilots now permitted in smart cities.",
     "idea", "Concept validated with 1 hyperscaler.", "Smart-city developers",
     "Heat-as-a-service contracts.", "If energy costs rise, heat has a buyer.",
     "Thermal systems leads ex-Caterpillar.", "co-founder"),

    ("SalineX", "Imran Sheikh", "https://linkedin.com/in/imransheikh", "https://salinex.in",
     ["water-tech", "materials-science"],
     "Coastal villages drink brackish water; RO is energy-hungry.",
     "Coastal India ~200M people; desalination ~$1.2B market.",
     "Membrane costs dropped; solar makes off-grid viable.",
     "prototype", "Solar still outputs 20L/day in field test.", "Panchayats",
     "Community units on O&M lease.", "If groundwater salinates, need is urgent.",
     "Chemical engineers ex-IIT Madras.", "seed funding"),

    ("PulseGrid", "Niharika Rao", "https://linkedin.com/in/niharikarao", "https://pulsegrid.io",
     ["grid-tech", "energy-storage"],
     "Renewable-heavy grids lack fast frequency response.",
     "India needs ~30GW flexible capacity by 2030.",
     "Ancillary-services markets now open to aggregators.",
     "pilot", "Aggregated 5MW of batteries in a demo.", "DISCOMs / exchanges",
     "Virtual power plant software + aggregator license.", "If markets pay for response, margin is steady.",
     "Power-market ex-regulator + ML lead.", "funding"),

    ("GreenFoundry", "Arnav Gupta", "https://linkedin.com/in/arnavgupta", "https://greenfoundry.earth",
     ["industrial-decarbonization", "carbon-capture"],
     "Foundries burn coke; switching to green reductants is unproven at scale.",
     "India ~10k foundries; decarbonization spend ~$4B.",
     "Buyers now demand scope-3 low-carbon castings.",
     "idea", "Lab reductant cuts emissions 60% in test.", "Auto / engineering OEMs",
     "Licensed process to foundries.", "If OEMs mandate low-carbon, offtake follows.",
     "Metallurgists ex-Tata.", "co-founder"),

    ("NanoShield", "Tara Desai", "https://linkedin.com/in/taradesai", "https://nanoshield.materials",
     ["nanorobotics", "materials-science"],
     "Building facades absorb heat, spiking cooling loads in hot cities.",
     "Cooling is ~20% of urban electricity; coatings ~$900M market.",
     "Nano-coatings now durable enough for exteriors.",
     "prototype", "Coating cuts surface temp 12C in trials.", "Real-estate developers",
     "B2B supply to paint/formulation firms.", "If heatwaves worsen, ROI is obvious.",
     "Nanotech PhDs ex-JNCASR.", "seed funding"),

    ("FlowMobility", "Dev Varma", "https://linkedin.com/in/devvarma", "https://flowmobility.in",
     ["sustainable-mobility", "energy-storage"],
     "Last-mile freight in cities still runs on diesel autos.",
     "Last-mile logistics ~$5B; electrification ~$1.5B.",
     "City EV mandates + charging density crossed a threshold.",
     "early revenue", "60 vehicles deployed, $140k revenue.", "E-commerce fleets",
     "Lease + charge model.", "If diesel bans expand, switch is forced.",
     "Auto-MBAs + EV ops veterans.", "funding"),

    ("AgriChain", "Ritu Agarwal", "https://linkedin.com/in/rituagarwal", "https://agrichain.farm",
     ["agritech-climate", "circular-economy"],
     "Post-harvest loss is invisible because supply chains are opaque.",
     "India loses ~$13B/yr post-harvest.",
     "Affordable IoT + UPI rails enable traceable logistics.",
     "pilot", "Tracked 8k tonnes across 3 states.", "Exporters / FPOs",
     "SaaS + device leasing.", "If traceability becomes export-required, adoption is mandatory.",
     "Supply-chain leads ex-Ninjakart.", "pilot partners"),

    ("SolarSkin", "Kabir Anand", "https://linkedin.com/in/kabiranand", "https://solarskin.energy",
     ["energy-storage", "materials-science"],
     "Rooftop solar underperforms in dust-heavy Indian summers.",
     "Rooftop degradation costs ~$300M/yr in lost yield.",
     "Self-cleaning films now last the panel lifetime.",
     "prototype", "Film holds 98% yield in 6-mo field test.", "EPC installers",
     "Film supplied to installers.", "If yield gap widens, payback is clear.",
     "Polymer scientists ex-IIT Delhi.", "seed funding"),
]


def _run_one(raw):
    """Run the pipeline for one startup in a thread with a hard timeout."""
    rec = store.create_submission(raw)
    res = agents.run_pipeline(rec)
    rec = store.get(rec["id"])
    rec["structured"] = res["structured"]
    rec["badges"] = res["badges"]
    rec["disclaimer"] = res["disclaimer"]
    rec["trace"] = res["trace"]
    if res["structured"] and "_raw" not in res["structured"]:
        sc = res["structured"]
        rec["published_card"] = {
            "startup_name": sc.get("startup_name", raw["startup_name"]),
            "tagline": sc.get("tagline", ""),
            "stage": sc.get("stage", raw["stage"]),
            "problem": sc.get("problem", ""),
            "opportunity_size": sc.get("opportunity_size", ""),
            "differentiator": sc.get("differentiator", ""),
            "solution": sc.get("solution", ""),
            "ask": sc.get("ask", ""),
            "subtheme_tags": raw["subtheme_tags"],
            "badges": res["badges"],
            "published_at": store.now_iso(),
        }
        rec["status"] = "published"
    else:
        rec["status"] = "review"
    store.update(rec["id"], rec)
    return rec["status"]


def main():
    import concurrent.futures as cf
    # resume: skip names already published
    already = {s["name"] for s in store.published()}
    remaining = [s for s in SEED if s[0] not in already]
    total = len(SEED)
    done = len(already)
    failed = []
    print(f"RESUME: {done}/{total} already published, {len(remaining)} to seed.", flush=True)

    with cf.ThreadPoolExecutor(max_workers=1) as ex:
        for i, s in enumerate(remaining):
            (name, founder, li, web, tags, prob, opp, why, stage, proof,
             adop, gtm, succ, edge, looking) = s
            raw = {
                "startup_name": name, "tagline": "", "founder_names": founder,
                "founder_linkedin": li, "website": web, "subtheme_tags": tags,
                "problem": prob, "opportunity_size": opp, "why_now": why,
                "stage": stage, "proof_of_work": proof, "early_adopters": adop,
                "gtm": gtm, "success_scenario": succ, "team_edge": edge,
                "looking_for": looking,
            }
            status = "review"
            for attempt in range(2):
                fut = ex.submit(_run_one, raw)
                try:
                    status = fut.result(timeout=140)
                    break
                except cf.TimeoutError:
                    # a hang: cancel if possible, mark and retry once
                    fut.cancel()
                    print(f"[{done+1}/{total}] {name:14} -> TIMEOUT (attempt {attempt+1})", flush=True)
                    continue
                except Exception as e:
                    print(f"[{done+1}/{total}] {name:14} -> FAILED: {type(e).__name__}: {str(e)[:120]}",
                          flush=True)
                    failed.append(name)
                    break
            if status in ("published", "review"):
                done += 1
                print(f"[{done}/{total}] {name:14} -> {status}", flush=True)
            else:
                failed.append(name)
    print(f"DONE. Seeded {done}/{total} startups. Failed: {failed or 'none'}", flush=True)


if __name__ == "__main__":
    main()
