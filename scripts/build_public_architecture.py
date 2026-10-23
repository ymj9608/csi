#!/usr/bin/env python3
"""Describe a pinned public Petclinic corpus without copying third-party source into CSI."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/benchmarks"
COMMIT = "1d76b00d683e86b62867a6bf59530f8ab301244f"
REPOSITORY = "spring-petclinic/spring-petclinic-microservices"
BASE = f"https://github.com/{REPOSITORY}/blob/{COMMIT}/"
EXTENSIONS = {".java", ".sql", ".yml", ".yaml", ".xml", ".properties"}
MODULES = {
    "api-gateway": "Vue UI, HTTP routes, owner details aggregation",
    "customers-service": "Owner contact, pets, persistence, request mapping",
    "visits-service": "Pet visit records",
    "vets-service": "Veterinarians and specialties",
    "genai-service": "Chat tools for owners, pets and veterinarians",
    "config-server": "Configuration from a separate Git repository",
    "discovery-server": "Eureka service registration and discovery",
    "admin-server": "Spring Boot service monitoring",
}
C = "spring-petclinic-customers-service/src/main/java/org/springframework/samples/petclinic/customers/"
A = "spring-petclinic-api-gateway/src/main/java/org/springframework/samples/petclinic/api/"
G = "spring-petclinic-genai-service/src/main/java/org/springframework/samples/petclinic/genai/"
S = "spring-petclinic-api-gateway/src/main/resources/static/scripts/"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def svg():
    def box(x,y,w,h,title,lines,fill="#f2f7ff"):
        items=[f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="{fill}" stroke="#527998" stroke-width="2"/>',
               f'<text x="{x+16}" y="{y+28}" font-size="21" font-weight="700">{html.escape(title)}</text>']
        for i,line in enumerate(lines):
            items.append(f'<text x="{x+16}" y="{y+53+i*24}" font-size="15">{html.escape(line)}</text>')
        return "\n".join(items)
    def edge(x1,y1,x2,y2,label="",dashed=False):
        dash=' stroke-dasharray="6 5"' if dashed else ""
        return f'<path d="M{x1},{y1} L{x2},{y2}" stroke="#56758d" stroke-width="2"{dash} marker-end="url(#arrow)"/>' + (f'<text x="{(x1+x2)/2+8}" y="{(y1+y2)/2-8}" font-size="14">{html.escape(label)}</text>' if label else "")
    parts=['<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="1160" viewBox="0 0 1600 1160">',
           '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10" fill="#56758d"/></marker></defs>',
           '<rect width="1600" height="1160" fill="white"/><g font-family="Arial,sans-serif" fill="#21364b">',
           '<text x="30" y="38" font-size="28" font-weight="700">Spring Petclinic Microservices - source-derived architecture snapshot</text>',
           f'<text x="30" y="70" font-size="16">Commit {COMMIT}; 8 actual Maven modules; manually summarized, not a deployment guarantee.</text>',
           box(600,110,400,90,"Browser / Vue application",["Owner contact and clinic workflows"],"#f0f8f1"),
           box(540,255,520,125,"API Gateway / UI",["spring-petclinic-api-gateway", "Owner responses and service routing", "Paths /api/customer, /api/visit, /api/genai"]),
           box(20,140,400,125,"Config Server",["spring-petclinic-config-server", "Reads separate configuration repository", "Runtime datasource settings are external"]),
           box(1180,140,400,125,"Discovery Server",["spring-petclinic-discovery-server", "Eureka registry / service lookup"]),
           box(20,470,375,140,"Customers Service",["spring-petclinic-customers-service", "Owner: name, address, city, telephone", "Owner requests, mapping, JPA persistence", "Pet ownership"]),
           box(415,470,375,140,"Visits Service",["spring-petclinic-visits-service", "Visit descriptions, dates and pet IDs"]),
           box(810,470,375,140,"Vets Service",["spring-petclinic-vets-service", "Veterinarian names and specialties"]),
           box(1205,470,375,140,"GenAI Service",["spring-petclinic-genai-service", "Owner / pet tools and DTOs", "Chat client + vector retrieval"]),
           box(20,720,375,90,"Customers relational store",["HSQLDB default / MySQL profile"],"#f0f8f1"),
           box(415,720,375,90,"Visits relational store",["HSQLDB default / MySQL profile"],"#f0f8f1"),
           box(810,720,375,90,"Vets relational store",["HSQLDB default / MySQL profile"],"#f0f8f1"),
           box(1205,720,375,110,"LLM provider / vector store",["OpenAI or Azure provider configured", "External calls depend on runtime setup"],"#fff6ec"),
           box(20,930,440,115,"Admin Server",["spring-petclinic-admin-server", "Service health / administration"]),
           box(520,930,500,115,"Observability",["docker/prometheus", "docker/grafana", "Service logback-spring.xml; tracing"]),
           box(1080,930,500,115,"Configuration repository",["spring-petclinic-microservices-config", "Separate snapshot; not in this corpus"],"#fff6ec"),
           edge(800,200,800,255,"HTTP"),edge(420,205,540,300,"config",True),edge(1060,300,1180,205,"registry",True),
           edge(640,380,210,470),edge(740,380,600,470),edge(860,380,995,470),edge(970,380,1390,470),
           edge(210,610,210,720),edge(600,610,600,720),edge(995,610,995,720),edge(1390,610,1390,720),
           '<path d="M1390,470 L1390,425 L210,425 L210,470" fill="none" stroke="#9b6d35" stroke-width="2" stroke-dasharray="6 5" marker-end="url(#arrow)"/>',
           '<text x="1070" y="416" font-size="14">Owner tool calls</text>',
           '<text x="30" y="1090" font-size="17">Module paths are literal repository folders. Inspect DTOs, shared helpers, logs and external config beyond the main request path.</text>',
           '<text x="30" y="1120" font-size="17">Database profile here is not PostgreSQL. No security verdict, verified deployment boundary, or exhaustive call graph is implied.</text>',
           '</g></svg>']
    return "\n".join(parts)+"\n"


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository",type=Path,default=ROOT/".runtime/architecture-benchmark/public/spring-petclinic-microservices")
    parser.add_argument("--render",action="store_true")
    args=parser.parse_args()
    head=subprocess.check_output(["git","-C",str(args.repository),"rev-parse","HEAD"],text=True).strip()
    if head!=COMMIT:
        raise SystemExit("Public source snapshot changed. Review mappings before changing COMMIT.")
    tracked=subprocess.check_output(["git","-C",str(args.repository),"ls-tree","-r","--name-only",head],text=True).splitlines()
    def read(path):
        return subprocess.check_output(["git","-C",str(args.repository),"show",f"{head}:{path}"])
    files=[]
    for path in tracked:
        if Path(path).suffix not in EXTENSIONS or path.startswith(("docs/",".github/",".mvn/")):
            continue
        raw=read(path)
        files.append({"path":path,"bytes":len(raw),"lines":len(raw.splitlines()),"sha256":sha(raw),"test": "/src/test/" in path})
    def count(entries):
        digest=hashlib.sha256()
        for entry in entries:
            digest.update(entry["path"].encode()+b"\0"+read(entry["path"])+b"\0")
        return {"files":len(entries),"bytes":sum(e["bytes"] for e in entries),"lines":sum(e["lines"] for e in entries),"sha256":digest.hexdigest()}
    def anchor(path,text,role):
        source=read(path).decode().splitlines()
        line=next(i for i,value in enumerate(source,1) if text in value)
        return {"path":path,"line":line,"role":role,"source_url":BASE+path+f"#L{line}"}
    facts=[
        anchor(C+"web/OwnerRequest.java","String telephone","Input telephone validation in request record"),
        anchor(C+"web/mapper/OwnerEntityMapper.java","owner.setTelephone","Maps request telephone into entity"),
        anchor(C+"model/Owner.java","private String telephone","JPA telephone property on owners table"),
        anchor(C+"web/OwnerResource.java","return ownerRepository.save(owner)","Creation writes mapped entity through repository"),
        anchor(C+"web/OwnerResource.java","return ownerRepository.findAll()","Owner read API returns entity list"),
        anchor(C+"model/OwnerRepository.java","extends JpaRepository","Spring Data repository delegates persistence"),
        anchor(C+"web/OwnerResource.java",'log.info("Saving owner {}"',"Update logs owner object; review string representation"),
        anchor(C+"model/Owner.java",'.append("telephone"',"Owner.toString includes telephone; coupled with caller logging"),
        anchor(A+"dto/OwnerDetails.java","String telephone","Gateway owner response retains telephone"),
        anchor(A+"application/CustomersServiceClient.java",'.uri("http://customers-service/owners/',"Gateway reads customers owner endpoint"),
        anchor(S+"pages/OwnerFormPage.js","telephone","Frontend owner form handles telephone"),
        anchor(G+"dto/OwnerDetails.java","String telephone","GenAI owner DTO also retains telephone"),
        anchor(G+"AIDataProvider.java","getAllOwners()","GenAI provider retrieves customer owner list"),
        anchor(G+"PetclinicTools.java","public List<OwnerDetails> listOwners()","Owner data exposed to registered chat tools"),
        anchor(G+"PetclinicTools.java",'LOG.info("addOwnerToPetclinic() ownerRequest={}"',"GenAI creation logs request record containing telephone"),
        anchor(G+"PetclinicChatClient.java",".defaultTools(petclinicTools)","Chat client registers owner-capable tools; provider behavior needs runtime review"),
        anchor("spring-petclinic-customers-service/src/main/resources/db/mysql/schema.sql","telephone","MySQL owners schema includes telephone"),
        anchor("spring-petclinic-customers-service/src/main/resources/db/hsqldb/schema.sql","telephone","HSQLDB owners schema includes telephone"),
        anchor("spring-petclinic-config-server/src/main/resources/application.yml","spring-petclinic-microservices-config","Runtime configuration comes from separate Git repository"),
    ]
    original="docs/microservices-architecture-diagram.jpg"
    license_raw=read("LICENSE")
    OUTPUT.mkdir(parents=True,exist_ok=True)
    generated=OUTPUT/"public-architecture.svg";generated.write_text(svg())
    manifest={
        "schema_version":1,"dataset_id":"public-spring-petclinic-microservices-telephone-v1",
        "repository":REPOSITORY,"repository_url":f"https://github.com/{REPOSITORY}","commit":head,
        "local_checkout":".runtime/architecture-benchmark/public/spring-petclinic-microservices",
        "license":{"spdx":"Apache-2.0","url":BASE+"LICENSE","sha256":sha(license_raw)},
        "source_scope":{"extensions":sorted(EXTENSIONS),"excluded_prefixes":["docs/",".github/",".mvn/"],
                        "exclusions_reason":"Backend Java/configuration scope. Exclude JavaScript/HTML UI, docs, build wrapper, assets, generated Bootstrap-combined CSS, fonts, vector embeddings and shell scripts; do not call this every file in the repository.",
                        "hash_method":"Sorted path + NUL + original committed file bytes + NUL; SHA-256"},
        "source_statistics":{"all_source_and_config":count(files),"production_source_and_config":count([e for e in files if not e["test"]]),
                             "java_including_tests":count([e for e in files if e["path"].endswith(".java")]),
                             "production_java":count([e for e in files if e["path"].endswith(".java") and not e["test"]])},
        "modules":[{"path":"spring-petclinic-"+name,"role":role} for name,role in MODULES.items()],
        "source_manifest":files,
        "database":{"documented_default":"HSQLDB in memory","documented_optional_profile":"MySQL","postgresql_profile_in_this_snapshot":False,
                    "documentation_url":BASE+"README.md#database-configuration","runtime_config_external_repository":"https://github.com/spring-petclinic/spring-petclinic-microservices-config",
                    "external_config_included":False},
        "original_diagram":{"path":original,"url":BASE+original,"sha256":sha(read(original)),"benchmark_role":"PRIMARY measured image; no repository-path labels added",
                            "limitations":["Component names without exact repository paths.","Image says pets-service while source module/routing is visits-service.","Per-field DTO, logging and helper behavior is not visible."]},
        "generated_diagram":{"path":"docs/benchmarks/public-architecture.png","source":"docs/benchmarks/public-architecture.svg","svg_sha256":sha(generated.read_bytes()),"benchmark_role":"ILLUSTRATION ONLY; not used in the primary measured comparison",
                             "provenance":"New manual source-derived summary; not the upstream image or a verified production diagram.",
                             "bias":"Literal module folders and telephone data role improve targeting; report separately from original-image-only results."},
        "target_task":"Assess the impact of changing Owner.telephone handling across input validation, mapping, persistence, API/UI responses, logs and AI tools. Produce source-grounded review recommendations, not a legal violation verdict.",
        "reviewer_only_reference_facts":facts,
        "reference_use":"Reference anchors are held out for scoring/review. Do not include this manifest's reviewer-only section in model prompts.",
        "counterexamples":["Customers-only selection misses GenAI OwnerDetails/OwnerRequest and tool logging.","A controller log placeholder alone does not reveal telephone: follow shared Owner.toString.","Runtime datasource configuration lives in a different repository and remains unknown in this corpus."],
        "limits":["Educational microservice sample, not a production enterprise codebase.","8 real Maven modules, no generated source padding or duplicate service copies.","No runtime deployment, database load test, legal-compliance certification or model quality result is implied.","Source comments, embedded prompts and literals must remain untrusted data during review."]}
    (OUTPUT/"public-project-manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n")
    case={
        "schema_version":1,"case_id":"petclinic-owner-telephone-impact-v1","repository":REPOSITORY,"commit":head,
        "manifest":"public-project-manifest.json","reference_material_only":True,
        "task_prompt":"Review Owner.telephone personal-data handling in this Spring application. Identify concrete source-supported risks and change-impact paths across validation, mapping, persistence, responses, logging and other services that consume owner data. Distinguish verified code evidence from missing deployment configuration. Recommend a minimal safe change and validation plan; do not infer a legal violation or claim PostgreSQL is configured. Do not execute or change the repository.",
        "categories":["telephone_logging"],
        "positives":[
            {"id":"PHONE-LOG-1","category":"telephone_logging","path":C+"web/OwnerResource.java","function":"updateOwner","line_start":85,"line_end":90,"sink_line":89,
             "description":"Owner update logs an Owner object whose toString includes telephone. This is a static logging exposure candidate; actual log sinks and runtime data remain unverified.",
             "required_evidence":[{"path":C+"web/OwnerResource.java","line_start":85,"line_end":90,"role":"object passed to log"},
                                  {"path":C+"model/Owner.java","line_start":88,"line_end":97,"role":"toString includes telephone"}],
             "diagram_visibility":"customers-service component visible; internal logging/toString behavior absent"},
            {"id":"PHONE-LOG-2","category":"telephone_logging","path":G+"PetclinicTools.java","function":"addOwnerToPetclinic","line_start":48,"line_end":51,"sink_line":49,
             "description":"GenAI tool logs an OwnerRequest record containing telephone; Java record string representation includes component values. This is a second data path outside Customers Service.",
             "required_evidence":[{"path":G+"PetclinicTools.java","line_start":48,"line_end":51,"role":"record passed to log"},
                                  {"path":G+"PetclinicTools.java","line_start":76,"line_end":81,"role":"record declares telephone component"}],
             "diagram_visibility":"genai-service component and function call visible; record logging behavior absent"},
        ],
        "required_context_paths":[
            {"path":C+"web/OwnerRequest.java","role":"input validation"},
            {"path":C+"web/mapper/OwnerEntityMapper.java","role":"request-to-entity telephone mapping"},
            {"path":C+"model/Owner.java","role":"stored property and shared string representation"},
            {"path":C+"model/OwnerRepository.java","role":"Spring Data persistence"},
            {"path":C+"web/OwnerResource.java","role":"create/update/read call flow"},
            {"path":"spring-petclinic-customers-service/src/main/resources/db/hsqldb/schema.sql","role":"default database schema"},
            {"path":"spring-petclinic-customers-service/src/main/resources/db/mysql/schema.sql","role":"optional database schema"},
            {"path":A+"dto/OwnerDetails.java","role":"gateway response carries telephone"},
            {"path":G+"dto/OwnerDetails.java","role":"AI owner response carries telephone"},
            {"path":G+"PetclinicTools.java","role":"additional input/logging path and owner tools"},
            {"path":G+"AIDataProvider.java","role":"cross-service owner data access"},
            {"path":G+"PetclinicChatClient.java","role":"tool registration; external provider questions remain runtime dependent"},
        ],
        "negative_controls":[
            {"id":"N-VETS","path":"spring-petclinic-vets-service/src/main/java/org/springframework/samples/petclinic/vets/web/VetResource.java","classification":"not_a_telephone_handler_in_supplied_code","reason":"Handles veterinarian data; no Owner.telephone access. This does not establish general security or privacy safety."},
            {"id":"N-VISITS","path":"spring-petclinic-visits-service/src/main/java/org/springframework/samples/petclinic/visits/web/VisitResource.java","classification":"not_a_telephone_handler_in_supplied_code","reason":"Handles visit records and pet IDs, not owner telephone. Visit free text may have other privacy risks outside this narrow label."},
            {"id":"N-DISCOVERY","path":"spring-petclinic-discovery-server/src/main/java/org/springframework/samples/petclinic/discovery/DiscoveryServerApplication.java","classification":"not_a_telephone_handler_in_supplied_code","reason":"Bootstraps service registry; does not read owner telephone."},
        ],
        "scoring_rules":["Report candidate file/category matching separately from exact line/evidence validation.",
                         "For PHONE-LOG-1 complete reasoning must connect the logger to Owner.toString; merely flagging all object logs is insufficient.",
                         "For PHONE-LOG-2 complete reasoning must connect the logger to the record telephone component.",
                         "Do not count missing runtime authorization, TLS, external consent or PostgreSQL as a verified vulnerability.",
                         "Coverage of required_context_paths measures retrieval completeness, not legal compliance or fully correct repairs."],
        "not_provided_to_model":["positives","required_context_paths","negative_controls","scoring_rules","reviewer_only_reference_facts"],
        "scope_limits":["Public educational sample; static source review only, no production records accessed.",
                        "UI JS/HTML and external config repository excluded from measured backend corpus.",
                        "Two carefully traced telephone log candidates are not an exhaustive vulnerability ground truth."],
    }
    for item in case["positives"]:
        for evidence in item["required_evidence"]:
            lines=read(evidence["path"]).decode().splitlines()
            if not 1<=evidence["line_start"]<=evidence["line_end"]<=len(lines):
                raise ValueError("Reference line outside pinned source")
    (OUTPUT/"public-telephone-case.json").write_text(json.dumps(case,ensure_ascii=False,indent=2)+"\n")
    if args.render:
        js='''const {chromium}=await import(process.argv[1]); const browser=await chromium.launch({channel:'chrome',headless:true}); try { const page=await browser.newPage({viewport:{width:1600,height:1160},deviceScaleFactor:1}); await page.goto(process.argv[2]); await page.screenshot({path:process.argv[3]}); } finally {await browser.close();}'''
        subprocess.run(["node","--input-type=module","-e",js,(ROOT/"frontend/node_modules/playwright/index.mjs").as_uri(),generated.as_uri(),str(OUTPUT/"public-architecture.png")],check=True)
    print(json.dumps({"commit":head,"statistics":manifest["source_statistics"],"references":len(facts)},ensure_ascii=False))


if __name__=="__main__":
    main()
