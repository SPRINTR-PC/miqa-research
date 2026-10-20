using System.Reactive.Concurrency;
using ReactiveUI.Builder;

namespace MiresSftpUploader.Test.Unit;

/// <summary>ReactiveUI must be initialised once; view-model tests run commands and notifications inline, without a UI thread.</summary>
[TestClass]
public static class ReactiveUiTestSetup
{
    [AssemblyInitialize]
    public static void Initialise(TestContext _) =>
        RxAppBuilder.CreateReactiveUIBuilder()
            .WithMainThreadScheduler(ImmediateScheduler.Instance)
            .WithTaskPoolScheduler(ImmediateScheduler.Instance)
            .WithCoreServices()
            .BuildApp();
}
