using HarmonyLib;

class ${mod_class_name} : GameModification
{
    private Harmony _harmony;

    public ${mod_class_name}(Mod mod) : base(mod)
    {
        Log("Registering ${mod_name}...");
    }

    public override void OnModInitialization(Mod mod)
    {
        Log("Initializing ${mod_name}...");

        PatchGame();
    }

    public override void OnModUnloaded()
    {
        Log("Unloading ${mod_name}...");

        _harmony?.UnpatchAll(_harmony.Id);
    }

    private void PatchGame()
    {
        Log("Patching...");

        _harmony = new Harmony("${mod_harmony_id}");
        _harmony.PatchAll();
    }
}
