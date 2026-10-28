using System.Reflection;
using MiresSftpUploader.ViewModels;

namespace MiresSftpUploader.Test.Unit;

/// <summary>The Run-driving view models are shared with the terminal UI and must not expose Avalonia types.</summary>
[TestClass]
public sealed class RunViewModelsAvaloniaFreeTests
{
    private const BindingFlags All = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static | BindingFlags.DeclaredOnly;

    [TestMethod]
    [DataRow(typeof(UploadPageViewModel))]
    [DataRow(typeof(LogPaneViewModel))]
    [DataRow(typeof(FileRowViewModel))]
    [DataRow(typeof(SourceItemViewModel))]
    [DataRow(typeof(HistoryPageViewModel))]
    [DataRow(typeof(RunItemViewModel))]
    [DataRow(typeof(HelpViewModel))]
    public void Members_use_no_Avalonia_types(Type viewModel)
    {
        var offenders = new List<string>();
        foreach (var member in viewModel.GetMembers(All))
        {
            Type[] types = member switch
            {
                PropertyInfo p => [p.PropertyType],
                FieldInfo f => [f.FieldType],
                MethodBase m => [.. m.GetParameters().Select(x => x.ParameterType), .. (m is MethodInfo mi ? new[] { mi.ReturnType } : [])],
                _ => [],
            };
            if (types.Any(t => t.Assembly.GetName().Name!.StartsWith("Avalonia", StringComparison.Ordinal)))
                offenders.Add(member.Name);
        }
        CollectionAssert.AreEqual(Array.Empty<string>(), offenders, $"{viewModel.Name} exposes Avalonia types");
    }
}
