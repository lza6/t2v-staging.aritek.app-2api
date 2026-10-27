import Java from "frida-java-bridge";
Java.perform(() => {
    send("[+] hook v5 stepwise");
    const HI = Java.use("ai.video.generator.text.video.apiservice.HeaderInterceptor");
    HI.intercept.implementation = function (chain: any) {
        send("S1: entered");
        const resp = this.intercept(chain);
        send("S2: got resp");
        try {
            const req = chain.f9486e.value;
            send("S3: req=" + req.f6419a.value.toString());
            try {
                const body = resp.f6451g.value;
                send("S4: body obj=" + body.$className);
                const s = body.string();
                send(`\n===== REQ ${req.f6419a.value.toString()}\n===== RESP ${resp.f6448d.value}\n${s}`);
            } catch (e1: any) { send("S4err: " + e1); }
        } catch (e: any) { send("Sxerr: " + e); }
        return resp;
    };
    send("[+] HOOKED v5");
});
