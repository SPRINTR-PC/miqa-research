using System;
using System.Reactive;
using System.Reactive.Linq;
using ReactiveUI;
using Terminal.Gui.ViewBase;

namespace MiresSftpUploader.SettingsTui;

/// <summary>
/// Where a failed command ends up. A command run from a key or a button must never take the whole interface down (an unobserved
/// <c>ThrownExceptions</c> makes ReactiveUI throw), so every fire-and-forget command goes through <c>Fire</c>, which shows the message in a dialog instead.
/// </summary>
public static class TuiErrors
{
    /// <summary>Runs the command with <paramref name="parameter"/> and routes its failure to <paramref name="onError"/>.</summary>
    public static void Fire<TParam, TResult>(this ReactiveCommand<TParam, TResult> command, TParam parameter, Action<Exception> onError)
    {
        var failures = command.ThrownExceptions.Subscribe(onError);
        command.Execute(parameter).Finally(failures.Dispose).Subscribe(_ => { }, _ => { }); // the error itself arrives through ThrownExceptions
    }

    /// <summary>Runs a command without a parameter and routes its failure to <paramref name="onError"/>.</summary>
    public static void Fire<TResult>(this ReactiveCommand<Unit, TResult> command, Action<Exception> onError) =>
        command.Fire(Unit.Default, onError);

    /// <summary>Runs the command with <paramref name="parameter"/> and shows its failure in the <see cref="SettingsTuiWindow"/> containing <paramref name="origin"/>.</summary>
    public static void Fire<TParam, TResult>(this ReactiveCommand<TParam, TResult> command, TParam parameter, View origin) =>
        command.Fire(parameter, e => Report(origin, e));

    /// <summary>Runs a command without a parameter and shows its failure in the <see cref="SettingsTuiWindow"/> containing <paramref name="origin"/>.</summary>
    public static void Fire<TResult>(this ReactiveCommand<Unit, TResult> command, View origin) => command.Fire(Unit.Default, e => Report(origin, e));

    /// <summary>Shows <paramref name="error"/> in the window above <paramref name="origin"/>; nowhere to show it means the error is dropped, not thrown.</summary>
    public static void Report(View origin, Exception error)
    {
        for (var v = origin; v is not null; v = v.SuperView)
        {
            if (v is not SettingsTuiWindow window) continue;
            window.ShowError(error);
            return;
        }
    }
}
